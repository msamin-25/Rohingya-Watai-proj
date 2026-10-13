import secrets

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import factory
from app.settings import REPO_ROOT, Settings
from rvb_ai.audio import write_wav

SR = 16000
PATTERNS = {
    "hello": [(300, 0.15), (500, 0.15), (800, 0.15), (1200, 0.15)],
    "thank_you": [(1200, 0.15), (800, 0.15), (500, 0.15), (300, 0.15)],
    "need_doctor": [(400, 0.12), (1500, 0.12), (400, 0.12), (1500, 0.12), (400, 0.12)],
    "unknown": [(250, 0.3), (3000, 0.1), (250, 0.3)],
}


def wav(name: str, seed: int = 0, gain: float = 0.5) -> bytes:
    """A synthetic, deterministic 'utterance' (no real voice data in tests)."""
    rng = np.random.default_rng(seed)
    parts = [np.zeros(4000)]
    for f, dur in PATTERNS[name]:
        n = int(dur * rng.uniform(0.92, 1.08) * SR)
        t = np.arange(n) / SR
        f *= rng.uniform(0.97, 1.03)
        parts.append(sum(np.sin(2 * np.pi * k * f * t) / k for k in (1, 2, 3)))
    parts.append(np.zeros(4000))
    x = np.concatenate(parts)
    x = gain * x / np.max(np.abs(x)) + rng.normal(0, 0.002, x.size)
    return write_wav(x, SR)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        admin_token=secrets.token_urlsafe(32),
        data_dir=tmp_path / "var",
        allowed_hosts=["testserver", "localhost", "127.0.0.1"],
        max_upload_bytes=2_000_000,
        frontend_index=tmp_path / "index.html",
        seed_path=REPO_ROOT / "data" / "phrases.seed.json",
    )


@pytest.fixture
def client(settings):
    settings.frontend_index.write_text(
        "<!doctype html><html><head><style>body{color:red}</style></head>"
        "<body><script>console.log('hi')</script></body></html>"
    )
    with TestClient(factory(settings)) as c:
        c.key = {"X-RVB-Key": settings.admin_token}
        yield c


def teach(client, phrase_id, seed, speaker="me", kind="teach", name=None):
    return client.post(
        "/api/v1/takes",
        headers=client.key,
        data={"kind": kind, "speaker": speaker, "phrase_id": phrase_id or ""},
        files={"audio": ("take.wav", wav(name or phrase_id, seed), "audio/wav")},
    )
