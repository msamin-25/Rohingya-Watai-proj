"""Template matching with dynamic time warping (DTW).

Each taught take becomes a template. A new recording is compared with every template, and
phrases are ranked by their closest template. Lower distance = more similar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

INF = math.inf


def _cost_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Euclidean distance between every frame of a and every frame of b."""
    sq = (a * a).sum(axis=1)[:, None] + (b * b).sum(axis=1)[None, :] - 2.0 * (a @ b.T)
    return np.sqrt(np.maximum(sq, 0.0))


def dtw_distance(a: np.ndarray, b: np.ndarray, band: float = 0.3, max_len_ratio: float = 2.5) -> float:
    """Length-normalised DTW distance with a Sakoe-Chiba style band.

    Rows are computed with a vectorised min-plus scan:
    D[i, j] = C[i, j] + min(D[i-1, j-1], D[i-1, j], D[i, j-1])
            = S[j] + cummin_k(A[k] - S[k-1])   where A[k] = min(D[i-1, k-1], D[i-1, k]), S = cumsum(C[i]).
    """
    n, m = len(a), len(b)
    if n == 0 or m == 0 or max(n, m) > max_len_ratio * min(n, m):
        return INF
    cost = _cost_matrix(a, b)
    prev = np.full(m, INF)
    for i in range(n):
        if n > 1:
            pos = i / (n - 1)
            lo = max(0, math.ceil((pos - band) * (m - 1) - 1e-9))
            hi = min(m - 1, math.floor((pos + band) * (m - 1) + 1e-9))
        else:
            lo, hi = 0, m - 1
        if i == 0:
            arrive = np.full(m, INF)
            arrive[0] = 0.0
        else:
            shifted = np.concatenate([[INF], prev[:-1]])
            arrive = np.minimum(shifted, prev)
        row = np.full(m, INF)
        c = cost[i, lo : hi + 1]
        s = np.cumsum(c)
        s_prev = np.concatenate([[0.0], s[:-1]])
        with np.errstate(invalid="ignore"):
            row[lo : hi + 1] = s + np.minimum.accumulate(arrive[lo : hi + 1] - s_prev)
        prev = row
    total = prev[m - 1]
    return float(total / (n + m)) if math.isfinite(total) else INF


@dataclass(frozen=True)
class Template:
    phrase_id: str
    features: np.ndarray
    take_id: str | None = None
    speaker: str | None = None


@dataclass(frozen=True)
class PhraseScore:
    """How close a recording is to one phrase."""

    phrase_id: str
    distance: float  # closest template
    second_distance: float  # second-closest template of the same phrase (INF if only one)
    n_templates: int


@dataclass
class Matcher:
    templates: list[Template] = field(default_factory=list)
    band: float = 0.3

    def add(self, template: Template) -> None:
        self.templates.append(template)

    def remove_take(self, take_id: str) -> None:
        self.templates = [t for t in self.templates if t.take_id != take_id]

    def phrase_ids(self) -> set[str]:
        return {t.phrase_id for t in self.templates}

    def rank(self, features: np.ndarray, exclude_take: str | None = None) -> list[PhraseScore]:
        """Phrases sorted from most to least similar."""
        per_phrase: dict[str, list[float]] = {}
        for t in self.templates:
            if exclude_take is not None and t.take_id == exclude_take:
                continue
            d = dtw_distance(features, t.features, band=self.band)
            per_phrase.setdefault(t.phrase_id, []).append(d)
        scores = []
        for pid, ds in per_phrase.items():
            ds.sort()
            scores.append(PhraseScore(pid, ds[0], ds[1] if len(ds) > 1 else INF, len(ds)))
        scores.sort(key=lambda s: (s.distance, s.phrase_id))
        return scores
