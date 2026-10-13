import os
import stat

import pytest
from conftest import teach, wav

from app.settings import Settings, read_dotenv

ADMIN_ROUTES = [
    ("get", "/api/v1/takes"),
    ("get", "/api/v1/export"),
    ("get", "/api/v1/auth/check"),
    ("delete", "/api/v1/takes?all=true"),
    ("post", "/api/v1/phrases"),
]


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
@pytest.mark.parametrize("key", [None, "wrong-key", ""])
def test_admin_routes_need_the_helper_key(client, method, path, key):
    headers = {} if key is None else {"X-RVB-Key": key}
    r = getattr(client, method)(path, headers=headers)
    assert r.status_code == 401


def test_teaching_needs_the_helper_key(client):
    r = client.post(
        "/api/v1/takes",
        data={"kind": "teach", "speaker": "me", "phrase_id": "hello"},
        files={"audio": ("a.wav", wav("hello"), "audio/wav")},
    )
    assert r.status_code == 401
    assert client.get("/api/v1/auth/check", headers=client.key).status_code == 204


def test_unknown_host_is_rejected(client):
    """Blocks DNS-rebinding attacks from other websites."""
    assert client.get("/api/v1/health", headers={"Host": "evil.example"}).status_code == 400


def test_no_cors_headers_are_sent(client):
    r = client.options(
        "/api/v1/interpret",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in r.headers


def test_security_headers_and_csp_hashes(client):
    r = client.get("/")
    csp = r.headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "script-src 'sha256-" in csp and "unsafe-inline" not in csp
    assert "frame-ancestors 'none'" in csp
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["permissions-policy"].startswith("microphone=(self)")
    assert client.get("/api/v1/health").headers["cache-control"] == "no-store"


def test_no_interactive_docs_page(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/api/docs").status_code == 404


def test_upload_size_limit(client, settings):
    big = b"RIFF" + b"\0" * (settings.max_upload_bytes + 10)
    r = client.post("/api/v1/interpret", files={"audio": ("a.wav", big, "audio/wav")})
    assert r.status_code == 413


@pytest.mark.parametrize("payload", [b"not audio", b"RIFF\x00\x00\x00\x00WAVEjunk"])
def test_garbage_audio_is_rejected(client, payload):
    r = client.post("/api/v1/interpret", files={"audio": ("a.wav", payload, "audio/wav")})
    assert r.status_code == 422


@pytest.mark.parametrize("speaker", ["../../etc", "<script>", "", "x" * 40])
def test_speaker_label_is_validated(client, speaker):
    assert teach(client, "hello", 0, speaker=speaker).status_code == 422


@pytest.mark.parametrize("take_id", ["../../db", "..%2F..%2Fdb", "0" * 31, "Z" * 32])
def test_take_ids_cannot_escape_storage(client, take_id):
    r = client.get(f"/api/v1/takes/{take_id}/audio", headers=client.key)
    assert r.status_code == 404


def test_audio_sent_for_interpretation_is_not_stored(client, settings):
    client.post("/api/v1/interpret", files={"audio": ("a.wav", wav("hello"), "audio/wav")})
    assert list((settings.data_dir / "takes").iterdir()) == []


def test_private_files_are_owner_only(client, settings):
    teach(client, "hello", 0)
    mode = lambda p: stat.S_IMODE(os.stat(p).st_mode)  # noqa: E731
    assert mode(settings.data_dir) == 0o700
    assert mode(settings.data_dir / "db.json") == 0o600
    assert all(mode(p) == 0o600 for p in (settings.data_dir / "takes").iterdir())


@pytest.mark.parametrize("token", ["", "short", "change-me-" + "x" * 40])
def test_weak_or_placeholder_token_refuses_to_start(monkeypatch, tmp_path, token):
    monkeypatch.setenv("RVB_ADMIN_TOKEN", token)
    with pytest.raises(RuntimeError, match="RVB_ADMIN_TOKEN"):
        Settings.load(env_file=tmp_path / "missing.env")


def test_dotenv_parser(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# comment\nA=1\nB='two'\nC=\"three\"\n\nbad line\n")
    assert read_dotenv(f) == {"A": "1", "B": "two", "C": "three"}
