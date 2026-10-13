"""The safety gate must never get weaker. These tests pin its behaviour."""

import math

import pytest

from rvb_ai.matcher import PhraseScore
from rvb_ai.phrases import load_seed
from rvb_ai.safety import SENSITIVE, Thresholds, decide

T = Thresholds(accept_distance=2.6, accept_margin=0.08, strong_distance=2.2, strong_margin=0.15)
CATS = {"hi": "general", "bye": "general", "doctor": "health", "lawyer": "legal", "help": "emergency"}


def s(pid, d, second=None, n=3):
    return PhraseScore(pid, d, d + 0.05 if second is None else second, n)


def test_defaults_are_valid_and_strong_is_stricter():
    t = Thresholds()
    assert t.strong_distance <= t.accept_distance
    assert t.strong_margin >= t.accept_margin


@pytest.mark.parametrize(
    "kwargs",
    [
        {"strong_distance": 3.0},  # strong looser than accept
        {"strong_margin": 0.01},  # strong margin looser than accept margin
        {"accept_distance": -1},
        {"accept_distance": math.inf},
        {"accept_margin": 1.0},
    ],
)
def test_invalid_thresholds_are_refused(kwargs):
    with pytest.raises(ValueError):
        Thresholds(**{**Thresholds().to_dict(), **kwargs})


def test_nothing_taught():
    assert decide([], CATS, T).status == "no_phrases"


def test_general_clear_match_is_shown():
    d = decide([s("hi", 2.0), s("bye", 2.8)], CATS, T)
    assert d.status == "match" and d.phrase_id == "hi" and d.shown


def test_far_from_everything_is_unsure():
    d = decide([s("hi", 2.9), s("bye", 3.0)], CATS, T)
    assert d.status == "unsure" and d.phrase_id is None


def test_infinite_distance_is_unsure():
    assert decide([s("hi", math.inf)], CATS, T).status == "unsure"


def test_general_too_close_to_another_phrase_is_unsure():
    d = decide([s("hi", 2.0), s("bye", 2.1)], CATS, T)
    assert d.status == "unsure"


def test_sensitive_strong_match_is_shown():
    d = decide([s("doctor", 2.0, second=2.1), s("hi", 2.8)], CATS, T)
    assert d.status == "match" and d.phrase_id == "doctor"


@pytest.mark.parametrize(
    "ranked",
    [
        [s("doctor", 2.4), s("hi", 3.2)],  # between strong and accept distance
        [s("doctor", 2.0), s("hi", 2.2)],  # margin too small for strong
        [s("doctor", 2.0, n=1, second=math.inf), s("hi", 2.9)],  # only one taught take
        [s("doctor", 2.0, second=2.7), s("hi", 2.9)],  # takes disagree
    ],
)
def test_sensitive_weak_match_asks_for_interpreter_and_hides_english(ranked):
    d = decide(ranked, CATS, T)
    assert d.status == "interpreter_needed"
    assert d.phrase_id is None and not d.shown
    assert d.category == "health"


def test_general_match_with_close_sensitive_competitor_asks_for_interpreter():
    d = decide([s("hi", 2.0), s("help", 2.25), s("bye", 2.9)], CATS, T)
    assert d.status == "interpreter_needed" and d.category == "emergency" and not d.shown


def test_every_sensitive_category_is_gated():
    assert SENSITIVE == {"health", "legal", "emergency"}
    for pid in ("doctor", "lawyer", "help"):
        assert decide([s(pid, 2.5), s("hi", 3.5)], CATS, T).status == "interpreter_needed"


def test_seed_phrases_are_english_only_and_valid():
    phrases = load_seed()
    assert len(phrases) >= 10
    assert {p.category for p in phrases} >= {"general", "health", "legal", "emergency"}
    for p in phrases:
        assert p.english.isascii(), p.id  # English text only; no transliterated Rohingya
