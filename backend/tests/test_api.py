import io
import json
import zipfile

from conftest import teach, wav

from rvb_ai.safety import Thresholds

LOOSE = Thresholds(accept_distance=50, accept_margin=0.0, strong_distance=50, strong_margin=0.0)


def test_health_and_phrases(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"
    data = client.get("/api/v1/phrases").json()
    ids = {p["id"] for p in data["phrases"]}
    assert {"hello", "need_doctor", "call_ambulance"} <= ids
    assert set(data["categories"]) == {"general", "health", "legal", "emergency"}
    assert all(p["teach_takes"] == 0 for p in data["phrases"])


def test_home_page_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "<script>" in r.text


def test_interpret_before_teaching(client):
    r = client.post("/api/v1/interpret", files={"audio": ("a.wav", wav("hello"), "audio/wav")})
    assert r.json() == {"status": "no_phrases"}


def test_teach_then_interpret_shows_english(client):
    for pid in ("hello", "thank_you"):
        for seed in range(3):
            assert teach(client, pid, seed).status_code == 201
    client.app.state.engine.thresholds = LOOSE
    r = client.post("/api/v1/interpret", files={"audio": ("a.wav", wav("thank_you", 99), "audio/wav")})
    assert r.json() == {"status": "match", "phrase_id": "thank_you", "english": "Thank you.", "category": "general"}
    counts = {p["id"]: p["teach_takes"] for p in client.get("/api/v1/phrases").json()["phrases"]}
    assert counts["hello"] == 3


def test_untaught_sound_is_not_shown_with_default_thresholds(client):
    for pid in ("hello", "thank_you"):
        for seed in range(3):
            teach(client, pid, seed)
    r = client.post("/api/v1/interpret", files={"audio": ("a.wav", wav("unknown", 5), "audio/wav")}).json()
    assert r["status"] == "unsure" and "english" not in r


def test_sensitive_phrase_needs_strong_match(client):
    teach(client, "need_doctor", 0)  # only one take -> never strong
    teach(client, "hello", 0)
    client.app.state.engine.thresholds = LOOSE
    r = client.post("/api/v1/interpret", files={"audio": ("a.wav", wav("need_doctor", 7), "audio/wav")}).json()
    assert r == {"status": "interpreter_needed", "category": "health"}


def test_quality_problems_are_explained(client):
    quiet = wav("hello", gain=0.0005)
    r = client.post("/api/v1/interpret", files={"audio": ("a.wav", quiet, "audio/wav")}).json()
    assert r["status"] == "too_quiet" and "closer" in r["message"]
    r = teach(client, "hello", 0, name="hello") and client.post(
        "/api/v1/takes",
        headers=client.key,
        data={"kind": "teach", "speaker": "me", "phrase_id": "hello"},
        files={"audio": ("a.wav", quiet, "audio/wav")},
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "too_quiet"


def test_test_takes_untaught_phrases_and_delete_by_speaker(client):
    teach(client, "hello", 0, speaker="me")
    teach(client, "hello", 1, speaker="friend")
    r = teach(client, None, 2, speaker="me", kind="test", name="unknown")
    assert r.status_code == 201 and r.json()["phrase_id"] is None
    assert len(client.get("/api/v1/takes", headers=client.key).json()["takes"]) == 3

    assert client.delete("/api/v1/takes", headers=client.key).status_code == 422  # no filter, no all=true
    assert client.delete("/api/v1/takes?speaker=me", headers=client.key).json() == {"deleted": 2}
    takes = client.get("/api/v1/takes", headers=client.key).json()["takes"]
    assert [t["speaker"] for t in takes] == ["friend"]
    assert len(client.app.state.engine.matcher.templates) == 1

    tid = takes[0]["id"]
    assert client.get(f"/api/v1/takes/{tid}/audio", headers=client.key).content.startswith(b"RIFF")
    assert client.delete(f"/api/v1/takes/{tid}", headers=client.key).json() == {"deleted": 1}
    assert client.delete(f"/api/v1/takes/{tid}", headers=client.key).status_code == 404


def test_teach_take_requires_known_phrase(client):
    assert teach(client, None, 0, name="hello").status_code == 422
    assert teach(client, "not_a_phrase", 0, name="hello").status_code == 404


def test_custom_phrase_lifecycle(client):
    r = client.post("/api/v1/phrases", headers=client.key, json={"english": "Where is the  bus?", "category": "general"})
    assert r.status_code == 201
    p = r.json()
    assert p["id"].startswith("custom_") and p["english"] == "Where is the bus?" and p["custom"]
    teach(client, p["id"], 0, name="hello")
    assert client.delete(f"/api/v1/phrases/{p['id']}", headers=client.key).json() == {"deleted_takes": 1}
    assert client.delete("/api/v1/phrases/hello", headers=client.key).status_code == 409
    bad = client.post("/api/v1/phrases", headers=client.key, json={"english": "x", "category": "other"})
    assert bad.status_code == 422


def test_export_zip_matches_eval_format(client, tmp_path):
    teach(client, "hello", 0)
    teach(client, None, 1, kind="test", name="unknown")
    r = client.get("/api/v1/export", headers=client.key)
    assert r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    manifest = json.loads(z.read("recordings/manifest.json"))
    assert manifest["format"] == "rvb-recordings/1"
    assert len(manifest["takes"]) == 2
    for t in manifest["takes"]:
        assert z.read(f"recordings/{t['file']}").startswith(b"RIFF")

    from rvb_ai.recordings import load

    z.extractall(tmp_path / "out")
    data = load(tmp_path / "out")
    assert len(data.takes) == 2 and data.takes[0].features.shape[1] == 26


def test_engine_reloads_templates_after_restart(client, settings):
    teach(client, "hello", 0)
    teach(client, "hello", 1)
    from app.main import factory

    app2 = factory(settings)
    assert len(app2.state.engine.matcher.templates) == 2
