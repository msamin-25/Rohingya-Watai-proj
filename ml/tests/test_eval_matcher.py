import json
import uuid

import pytest
from synth import PATTERNS, SR, utterance

from rvb_ai import eval_matcher
from rvb_ai.audio import write_wav


def _export(tmp_path, tests=True):
    """Build a folder in the same format as the app's .zip export."""
    root = tmp_path / "rec"
    (root / "takes").mkdir(parents=True)
    names = list(PATTERNS)
    taught, untaught = names[:4], names[4]
    cats = {"rise": "general", "fall": "general", "hop": "health", "long": "general", "buzz": "general"}
    takes = []

    def add(pid, kind, speaker, x):
        tid = uuid.uuid4().hex
        (root / "takes" / f"{tid}.wav").write_bytes(write_wav(x, SR))
        takes.append({"id": tid, "phrase_id": pid, "kind": kind, "speaker": speaker, "file": f"takes/{tid}.wav"})

    for n in taught:
        for seed in range(3):
            add(n, "teach", "me", utterance(n, seed=seed))
        if tests:
            for seed in (50, 51, 52):
                add(n, "test", "me", utterance(n, seed=seed))
    if tests:
        add(None, "test", "me", utterance(untaught, seed=9))
    manifest = {
        "format": "rvb-recordings/1",
        "phrases": [{"id": n, "english": n.title(), "category": cats[n]} for n in names],
        "takes": takes,
    }
    (root / "manifest.json").write_text(json.dumps(manifest))
    return root


def test_cli_reports_metrics_and_never_shows_untaught(tmp_path, capsys):
    root = _export(tmp_path)
    assert eval_matcher.main([str(root), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    m = out["metrics"]
    assert m["known_trials"] == 12 and m["untaught_trials"] == 1
    assert m["top1_accuracy"] == 1.0
    assert m["untaught_shown"] == 0
    assert m["sensitive_wrong_shown"] == 0
    assert out["suggestion"]["wrong_shown"] == 0


def test_cli_human_report_and_parent_folder(tmp_path, capsys):
    _export(tmp_path)
    assert eval_matcher.main([str(tmp_path)]) == 0  # finds rec/manifest.json one level down
    text = capsys.readouterr().out
    assert "Top-1 accuracy" in text and "WRONG and shown" in text and "NOT applied" in text


def test_leave_one_out_when_no_test_takes(tmp_path, capsys):
    root = _export(tmp_path, tests=False)
    assert eval_matcher.main([str(root), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["mode"].startswith("leave-one-out")
    assert out["metrics"]["trials"] == 12


def test_manifest_cannot_point_outside_the_folder(tmp_path, capsys):
    root = _export(tmp_path)
    m = json.loads((root / "manifest.json").read_text())
    m["takes"][0]["file"] = "../../etc/passwd"
    (root / "manifest.json").write_text(json.dumps(m))
    assert eval_matcher.main([str(root)]) == 2
    assert "Unsafe file path" in capsys.readouterr().err


def test_missing_folder(tmp_path, capsys):
    assert eval_matcher.main([str(tmp_path)]) == 2
    with pytest.raises(SystemExit):
        eval_matcher.main(["--help"])
