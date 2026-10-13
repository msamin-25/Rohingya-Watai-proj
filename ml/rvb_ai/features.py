"""Speech features: silence trimming + MFCC + deltas + per-utterance CMVN.

PARITY: frontend/src/js/dsp.js is a line-by-line port of this file. If you change a constant
or a step here, change dsp.js the same way and run ml/tests/test_parity.py.
"""

from __future__ import annotations

import math

import numpy as np

from .audio import SAMPLE_RATE, resample_linear

FRAME_LEN = 400  # 25 ms at 16 kHz
HOP = 160  # 10 ms
N_FFT = 512
N_MELS = 26
N_MFCC = 13
PREEMPH = 0.97
FMIN = 20.0
FMAX = 8000.0
TRIM_TOP_DB = 35.0  # frames quieter than (loudest - 35 dB) count as silence
TRIM_FLOOR_DB = -60.0  # ...and anything below -60 dBFS always counts as silence
TRIM_PAD_FRAMES = 5
EPS = 1e-10
FEATURE_DIM = 2 * N_MFCC


def _n_frames(n_samples: int) -> int:
    return 1 + (n_samples - FRAME_LEN) // HOP if n_samples >= FRAME_LEN else 1


def _frames(x: np.ndarray) -> np.ndarray:
    if x.size < FRAME_LEN:
        x = np.concatenate([x, np.zeros(FRAME_LEN - x.size)])
    n = _n_frames(x.size)
    idx = np.arange(FRAME_LEN)[None, :] + HOP * np.arange(n)[:, None]
    return x[idx]


def frame_db(x: np.ndarray) -> np.ndarray:
    """RMS level of each frame in dBFS."""
    rms = np.sqrt(np.mean(_frames(np.asarray(x, dtype=np.float64)) ** 2, axis=1))
    return 20.0 * np.log10(np.maximum(rms, EPS))


def trim_bounds(x: np.ndarray) -> tuple[int, int]:
    """[start, end) sample range that contains speech; (0, 0) if there is none."""
    x = np.asarray(x, dtype=np.float64)
    if x.size == 0:
        return 0, 0
    db = frame_db(x)
    floor = max(float(db.max()) - TRIM_TOP_DB, TRIM_FLOOR_DB)
    voiced = np.flatnonzero(db > floor)
    if voiced.size == 0:
        return 0, 0
    start = max(0, (int(voiced[0]) - TRIM_PAD_FRAMES) * HOP)
    end = min(x.size, (int(voiced[-1]) + TRIM_PAD_FRAMES) * HOP + FRAME_LEN)
    return start, end


def _hz_to_mel(f: np.ndarray | float) -> np.ndarray | float:
    return 2595.0 * np.log10(1.0 + np.asarray(f) / 700.0)


def _mel_to_hz(m: np.ndarray) -> np.ndarray:
    return 700.0 * (10.0 ** (m / 2595.0) - 1.0)


def mel_filterbank() -> np.ndarray:
    """(N_MELS, N_FFT//2+1) triangular filters on a continuous frequency axis (HTK mel scale)."""
    hz = _mel_to_hz(np.linspace(_hz_to_mel(FMIN), _hz_to_mel(FMAX), N_MELS + 2))
    freqs = np.arange(N_FFT // 2 + 1) * SAMPLE_RATE / N_FFT
    fb = np.zeros((N_MELS, freqs.size))
    for m in range(N_MELS):
        lo, mid, hi = hz[m], hz[m + 1], hz[m + 2]
        up = (freqs - lo) / (mid - lo)
        down = (hi - freqs) / (hi - mid)
        fb[m] = np.maximum(0.0, np.minimum(up, down))
    return fb


def dct_matrix() -> np.ndarray:
    """(N_MFCC, N_MELS) orthonormal DCT-II."""
    k = np.arange(N_MFCC)[:, None]
    n = np.arange(N_MELS)[None, :]
    d = np.sqrt(2.0 / N_MELS) * np.cos(math.pi * k * (2 * n + 1) / (2 * N_MELS))
    d[0] *= 1.0 / math.sqrt(2.0)
    return d


_FB = mel_filterbank()
_DCT = dct_matrix()
_WINDOW = 0.54 - 0.46 * np.cos(2.0 * math.pi * np.arange(FRAME_LEN) / (FRAME_LEN - 1))


def mfcc(x: np.ndarray) -> np.ndarray:
    """(T, N_MFCC) MFCCs of 16 kHz samples."""
    x = np.asarray(x, dtype=np.float64)
    y = x.copy()
    y[1:] = x[1:] - PREEMPH * x[:-1]
    frames = _frames(y) * _WINDOW
    power = np.abs(np.fft.rfft(frames, n=N_FFT, axis=1)) ** 2 / N_FFT
    logmel = np.log(np.maximum(power @ _FB.T, EPS))
    return logmel @ _DCT.T


def deltas(c: np.ndarray) -> np.ndarray:
    """First-order deltas: (c[t+1] - c[t-1]) / 2 with edge frames repeated."""
    padded = np.concatenate([c[:1], c, c[-1:]], axis=0)
    return (padded[2:] - padded[:-2]) / 2.0


def cmvn(f: np.ndarray) -> np.ndarray:
    """Per-utterance mean and variance normalisation, per dimension."""
    return (f - f.mean(axis=0)) / (f.std(axis=0) + 1e-8)


def extract(x: np.ndarray, rate: int = SAMPLE_RATE) -> np.ndarray:
    """Full pipeline: resample -> trim silence -> MFCC + deltas -> CMVN. Returns (T, FEATURE_DIM)."""
    x16 = resample_linear(x, rate)
    start, end = trim_bounds(x16)
    if end <= start:
        x16 = x16[:FRAME_LEN]
    else:
        x16 = x16[start:end]
    c = mfcc(x16)
    return cmvn(np.concatenate([c, deltas(c)], axis=1))
