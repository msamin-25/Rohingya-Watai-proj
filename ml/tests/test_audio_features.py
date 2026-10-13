import numpy as np
import pytest
from synth import SR, utterance

from rvb_ai import audio, features


def test_wav_roundtrip_is_lossless_at_16_bit():
    x = utterance("rise")
    y, rate = audio.read_wav(audio.write_wav(x, SR))
    assert rate == SR
    assert np.max(np.abs(x - y)) < 1 / 16000


def test_read_wav_rejects_garbage_and_too_long():
    with pytest.raises(audio.AudioError):
        audio.read_wav(b"not a wav file")
    with pytest.raises(audio.AudioError):
        audio.read_wav(audio.write_wav(np.zeros(SR * 16), SR))


def test_stereo_is_mixed_to_mono():
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.array([1000, -1000] * 100, dtype="<i2").tobytes())
    x, _ = audio.read_wav(buf.getvalue())
    assert x.shape == (100,) and np.allclose(x, 0)


def test_resample_linear_length_and_identity():
    x = np.sin(np.arange(4800) / 10)
    assert audio.resample_linear(x, 48000).size == 1600
    assert np.array_equal(audio.resample_linear(x, SR), x)


def test_trim_finds_speech_inside_silence():
    x = np.concatenate([np.zeros(SR), utterance("rise", noise=0), np.zeros(SR)])
    start, end = features.trim_bounds(x)
    assert SR * 0.9 < start < SR * 1.3
    assert x.size - SR * 1.3 < end < x.size - SR * 0.9


def test_trim_of_silence_is_empty():
    assert features.trim_bounds(np.zeros(SR)) == (0, 0)


def test_extract_shape_and_normalisation():
    f = features.extract(utterance("hop"), SR)
    assert f.shape[1] == features.FEATURE_DIM == 26
    assert 40 < f.shape[0] < 120
    assert np.allclose(f.mean(axis=0), 0, atol=1e-9)


def test_extract_is_deterministic_and_handles_tiny_input():
    x = utterance("fall", seed=3)
    assert np.array_equal(features.extract(x, SR), features.extract(x, SR))
    assert features.extract(np.zeros(10), SR).shape == (1, 26)


def test_filterbank_has_no_empty_filters():
    fb = features.mel_filterbank()
    assert fb.shape == (26, 257)
    assert (fb.sum(axis=1) > 0).all()


def test_quality_flags():
    assert audio.quality(utterance("rise"), SR).problem is None
    assert audio.quality(np.zeros(SR), SR).problem == "too_quiet"
    assert audio.quality(utterance("rise")[: SR // 2 - 2000], SR).problem == "too_short"
    assert audio.quality(utterance("rise", gain=0.001, noise=0), SR).problem == "too_quiet"
    assert audio.quality(np.clip(utterance("rise", gain=5), -1, 1), SR).problem == "too_loud"
