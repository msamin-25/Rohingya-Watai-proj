import math

import numpy as np
import pytest
from synth import PATTERNS, SR, utterance

from rvb_ai.features import extract
from rvb_ai.matcher import Matcher, Template, dtw_distance


def _dtw_reference(a, b):
    """Plain O(n*m) DTW without a band, to check the vectorised version."""
    n, m = len(a), len(b)
    D = np.full((n + 1, m + 1), math.inf)
    D[0, 0] = 0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c = np.linalg.norm(a[i - 1] - b[j - 1])
            D[i, j] = c + min(D[i - 1, j - 1], D[i - 1, j], D[i, j - 1])
    return D[n, m] / (n + m)


def test_dtw_matches_reference_when_band_is_wide():
    rng = np.random.default_rng(1)
    a, b = rng.normal(size=(17, 4)), rng.normal(size=(23, 4))
    assert math.isclose(dtw_distance(a, b, band=1.0), _dtw_reference(a, b), rel_tol=1e-9)


def test_dtw_identity_symmetry_and_band_is_never_lower():
    rng = np.random.default_rng(2)
    a, b = rng.normal(size=(30, 5)), rng.normal(size=(40, 5))
    assert dtw_distance(a, a) == pytest.approx(0, abs=1e-6)
    assert math.isclose(dtw_distance(a, b), dtw_distance(b, a), rel_tol=1e-9)
    assert dtw_distance(a, b, band=0.2) >= dtw_distance(a, b, band=1.0) - 1e-12


def test_dtw_rejects_very_different_lengths():
    rng = np.random.default_rng(3)
    assert dtw_distance(rng.normal(size=(10, 3)), rng.normal(size=(40, 3))) == math.inf
    assert dtw_distance(np.zeros((0, 3)), np.zeros((5, 3))) == math.inf


def _trained():
    m = Matcher()
    for name in PATTERNS:
        for seed in range(3):
            m.add(Template(name, extract(utterance(name, seed=seed), SR), f"{name}-{seed}"))
    return m


def test_matcher_recognises_new_takes_of_each_pattern():
    m = _trained()
    for name in PATTERNS:
        ranked = m.rank(extract(utterance(name, seed=100, speed=1.1), SR))
        assert ranked[0].phrase_id == name
        assert ranked[0].n_templates == 3
        assert ranked[0].distance <= ranked[0].second_distance


def test_remove_take_and_leave_one_out():
    m = _trained()
    m.remove_take("rise-0")
    assert sum(t.phrase_id == "rise" for t in m.templates) == 2
    ranked = m.rank(m.templates[0].features, exclude_take=m.templates[0].take_id)
    assert ranked[0].distance > 0
