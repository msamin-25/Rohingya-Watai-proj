# rvb_ai

The ML core of the Rohingya Voice Interpreter. See the
[architecture section of the project README](../README.md#architecture-at-a-glance).

| Module | Job |
|---|---|
| `audio.py` | Read and write 16-bit PCM WAV, linear resampling, quality checks |
| `features.py` | Silence trimming and MFCC + delta features with per-utterance CMVN (ported 1:1 to `frontend/src/js/dsp.js`) |
| `matcher.py` | Banded DTW distance and a template matcher that ranks taught phrases |
| `safety.py` | Thresholds and the safety gate that decides what may be shown |
| `phrases.py` | Loads `data/phrases.seed.json` |
| `recordings.py` | Reads an exported recordings folder (`manifest.json` + WAVs) |
| `eval_matcher.py` | `python -m rvb_ai.eval_matcher recordings/`: accuracy, wrong-and-shown rate, confusions, threshold evidence |
