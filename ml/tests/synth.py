"""Deterministic synthetic 'utterances' for tests: no real voices are needed or stored."""

from __future__ import annotations

import numpy as np

SR = 16000

# Each pattern is a sequence of (frequency_hz, seconds) segments, like crude syllables.
PATTERNS: dict[str, list[tuple[float, float]]] = {
    "rise": [(300, 0.15), (500, 0.15), (800, 0.15), (1200, 0.15)],
    "fall": [(1200, 0.15), (800, 0.15), (500, 0.15), (300, 0.15)],
    "hop": [(400, 0.12), (1500, 0.12), (400, 0.12), (1500, 0.12), (400, 0.12)],
    "long": [(600, 0.4), (2000, 0.4)],
    "buzz": [(250, 0.3), (3000, 0.1), (250, 0.3)],
}


def utterance(name: str, seed: int = 0, speed: float = 1.0, noise: float = 0.002, gain: float = 0.5) -> np.ndarray:
    """Harmonic tones following the pattern, with silence around and small random variations."""
    rng = np.random.default_rng(seed)
    parts = [np.zeros(int(0.25 * SR))]
    phase = 0.0
    for f, dur in PATTERNS[name]:
        n = int(dur * speed * rng.uniform(0.92, 1.08) * SR)
        f = f * rng.uniform(0.97, 1.03)
        t = np.arange(n) / SR
        seg = sum(np.sin(2 * np.pi * k * f * t + phase) / k for k in (1, 2, 3))
        phase += 2 * np.pi * f * n / SR
        env = np.minimum(1.0, np.minimum(np.arange(n), np.arange(n)[::-1]) / (0.01 * SR))
        parts.append(seg * env)
    parts.append(np.zeros(int(0.25 * SR)))
    x = np.concatenate(parts)
    x = gain * x / np.max(np.abs(x))
    return x + rng.normal(0.0, noise, x.size)
