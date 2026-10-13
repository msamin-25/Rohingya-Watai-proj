"""The safety gate: decides whether an English phrase may be shown.

Rules (do not weaken):
* "Not sure" is always better than a wrong answer.
* Health, legal and emergency phrases are shown only on a STRONG match: closer than
  strong_distance, a clear margin over every other phrase, and at least two taught takes
  of that phrase that both agree.
* If a sensitive phrase is a close competitor of a general match, we do not show the general
  phrase either; we ask for a human interpreter.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .matcher import PhraseScore

CATEGORIES = ("general", "health", "legal", "emergency")
SENSITIVE = frozenset({"health", "legal", "emergency"})


@dataclass(frozen=True)
class Thresholds:
    """DTW distance / margin thresholds. Calibrate with `python -m rvb_ai.eval_matcher`."""

    accept_distance: float = 2.6
    accept_margin: float = 0.08
    strong_distance: float = 2.2
    strong_margin: float = 0.15

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite, non-negative number")
        if not (self.accept_margin < 1 and self.strong_margin < 1):
            raise ValueError("margins must be below 1")
        if self.strong_distance > self.accept_distance:
            raise ValueError("strong_distance must not be looser than accept_distance")
        if self.strong_margin < self.accept_margin:
            raise ValueError("strong_margin must not be looser than accept_margin")

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class Decision:
    status: str  # "match" | "unsure" | "interpreter_needed" | "no_phrases"
    phrase_id: str | None = None  # set only when status == "match"
    category: str | None = None  # for interpreter_needed: which sensitive area it may be about
    distance: float | None = None
    margin: float | None = None
    reason: str = ""

    @property
    def shown(self) -> bool:
        return self.status == "match"


def margin_of(ranked: list[PhraseScore]) -> float:
    """Relative gap between the best phrase and the next-best different phrase (0..1)."""
    if not ranked or not math.isfinite(ranked[0].distance):
        return 0.0
    if len(ranked) < 2 or not math.isfinite(ranked[1].distance) or ranked[1].distance <= 0:
        return 1.0
    return max(0.0, (ranked[1].distance - ranked[0].distance) / ranked[1].distance)


def decide(ranked: list[PhraseScore], categories: dict[str, str], t: Thresholds) -> Decision:
    if not ranked:
        return Decision("no_phrases", reason="No phrases have been taught yet.")
    best = ranked[0]
    d1 = best.distance
    margin = margin_of(ranked)
    category = categories.get(best.phrase_id, "general")
    common = {"distance": d1 if math.isfinite(d1) else None, "margin": margin}

    if not math.isfinite(d1) or d1 > t.accept_distance:
        return Decision("unsure", reason="Not close to any taught phrase.", **common)

    if category in SENSITIVE:
        strong = (
            d1 <= t.strong_distance
            and margin >= t.strong_margin
            and best.n_templates >= 2
            and best.second_distance <= t.accept_distance
        )
        if strong:
            return Decision("match", best.phrase_id, category, reason="Strong match.", **common)
        return Decision(
            "interpreter_needed", category=category, reason="Possible sensitive phrase, not a strong match.", **common
        )

    if margin < t.accept_margin:
        return Decision("unsure", reason="Too close to another phrase.", **common)

    # A general match must not hide a close sensitive competitor.
    for other in ranked[1:]:
        if not math.isfinite(other.distance) or other.distance <= 0:
            break
        if (other.distance - d1) / other.distance >= t.strong_margin:
            break
        other_cat = categories.get(other.phrase_id, "general")
        if other_cat in SENSITIVE:
            return Decision(
                "interpreter_needed",
                category=other_cat,
                reason="A sensitive phrase is too close to call.",
                **common,
            )

    return Decision("match", best.phrase_id, category, reason="Match.", **common)
