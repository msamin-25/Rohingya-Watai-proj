"""frontend/src/js/dsp.js must compute the same numbers as rvb_ai.features / rvb_ai.audio."""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from synth import SR, utterance

from rvb_ai import audio, features

RUNNER = Path(__file__).with_name("parity_runner.mjs")
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required for the parity test (install Node 20+)")


def _signals():
    rng = np.random.default_rng(7)
    return [
        (utterance("rise", seed=1), SR),
        (utterance("hop", seed=2, noise=0.01), SR),
        (np.concatenate([np.zeros(3000), rng.normal(0, 0.2, 9000), np.zeros(5000)]), SR),
        (audio.resample_linear(utterance("long", seed=3), SR, 48000), 48000),  # browser-like rate
        (utterance("fall", seed=4)[:300], SR),  # shorter than one frame
        (np.zeros(4000), SR),  # silence
    ]


def test_dsp_js_matches_python():
    sigs = _signals()
    payload = json.dumps({"signals": [{"x": x.tolist(), "rate": r} for x, r in sigs]})
    proc = subprocess.run([NODE, str(RUNNER)], input=payload, capture_output=True, text=True, timeout=120, check=True)
    results = json.loads(proc.stdout)

    for (x, rate), js in zip(sigs, results):
        x16 = audio.resample_linear(x, rate)
        np.testing.assert_allclose(js["resampled"], x16, rtol=0, atol=1e-12)
        assert tuple(js["trim"]) == features.trim_bounds(x16)

        py = features.extract(x, rate)
        got = np.array(js["features"])
        assert got.shape == py.shape
        np.testing.assert_allclose(got, py, rtol=1e-6, atol=1e-6)

        q = audio.quality(x, rate)
        assert js["quality"]["problem"] == q.problem
        assert js["quality"]["voicedS"] == pytest.approx(q.voiced_s)
        assert js["quality"]["rmsDb"] == pytest.approx(q.rms_db, abs=1e-6)
        assert js["quality"]["peakDb"] == pytest.approx(q.peak_db, abs=1e-6)
