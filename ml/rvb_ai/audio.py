"""WAV input/output, resampling and recording quality checks (stdlib + numpy only)."""

from __future__ import annotations

import io
import math
import wave
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16000
MIN_SAMPLE_RATE = 8000
MAX_SAMPLE_RATE = 48000
MAX_SECONDS = 15.0


class AudioError(ValueError):
    """The audio cannot be used (wrong format, too long, empty...)."""


def read_wav(data: bytes, max_seconds: float = MAX_SECONDS) -> tuple[np.ndarray, int]:
    """Decode PCM WAV bytes into mono float64 samples in [-1, 1] and the sample rate."""
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            channels = w.getnchannels()
            width = w.getsampwidth()
            rate = w.getframerate()
            n = w.getnframes()
            if w.getcomptype() != "NONE":
                raise AudioError("Only uncompressed PCM WAV is supported.")
            if channels not in (1, 2):
                raise AudioError("Audio must be mono or stereo.")
            if width not in (1, 2, 4):
                raise AudioError("Audio must be 8, 16 or 32-bit PCM.")
            if not MIN_SAMPLE_RATE <= rate <= MAX_SAMPLE_RATE:
                raise AudioError(f"Sample rate must be {MIN_SAMPLE_RATE}-{MAX_SAMPLE_RATE} Hz.")
            if n / rate > max_seconds:
                raise AudioError(f"Recording is longer than {max_seconds:g} seconds.")
            raw = w.readframes(n)
    except (wave.Error, EOFError) as exc:
        raise AudioError("Not a valid WAV file.") from exc

    if width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    elif width == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    else:
        x = np.frombuffer(raw, dtype="<i4").astype(np.float64) / 2147483648.0
    if channels == 2:
        x = x[: len(x) // 2 * 2].reshape(-1, 2).mean(axis=1)
    if x.size == 0:
        raise AudioError("Recording is empty.")
    return x, rate


def write_wav(samples: np.ndarray, rate: int = SAMPLE_RATE) -> bytes:
    """Encode mono float samples in [-1, 1] as 16-bit PCM WAV bytes."""
    pcm = np.clip(np.asarray(samples, dtype=np.float64), -1.0, 1.0)
    pcm = np.where(pcm < 0, pcm * 32768.0, pcm * 32767.0).round().astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def resample_linear(x: np.ndarray, rate_in: int, rate_out: int = SAMPLE_RATE) -> np.ndarray:
    """Linear-interpolation resampler. Mirrored exactly by resampleLinear() in dsp.js."""
    x = np.asarray(x, dtype=np.float64)
    if rate_in == rate_out or x.size == 0:
        return x.copy()
    n_out = int(math.floor(x.size * rate_out / rate_in + 0.5))
    t = np.arange(n_out, dtype=np.float64) * (rate_in / rate_out)
    return np.interp(t, np.arange(x.size, dtype=np.float64), x)


@dataclass(frozen=True)
class Quality:
    duration_s: float
    voiced_s: float
    rms_db: float  # level of the speech part
    peak_db: float  # loudest 25 ms frame
    clipped_fraction: float

    @property
    def problem(self) -> str | None:
        """A short machine-readable reason the take should be redone, or None."""
        if self.peak_db < -45.0 or self.rms_db < -50.0:
            return "too_quiet"
        if self.voiced_s < 0.25:
            return "too_short"
        if self.clipped_fraction > 0.02:
            return "too_loud"
        return None


def quality(x: np.ndarray, rate: int) -> Quality:
    from .features import frame_db, trim_bounds  # local import avoids a cycle

    x16 = resample_linear(x, rate)
    start, end = trim_bounds(x16)
    voiced = x16[start:end]
    rms = float(np.sqrt(np.mean(voiced**2))) if voiced.size else 0.0
    return Quality(
        duration_s=x.size / rate,
        voiced_s=voiced.size / SAMPLE_RATE,
        rms_db=20.0 * math.log10(max(rms, 1e-10)),
        peak_db=float(frame_db(x16).max()) if x16.size else -200.0,
        clipped_fraction=float(np.mean(np.abs(x) >= 0.999)) if x.size else 0.0,
    )
