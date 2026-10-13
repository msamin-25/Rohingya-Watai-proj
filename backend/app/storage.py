"""Local, private storage for taught phrases and recorded takes.

Layout (all under RVB_DATA_DIR, default ./var, git-ignored):
    db.json           phrases added in the app + metadata of every take
    takes/<id>.wav    the recordings themselves
Audio sent for interpretation is never stored.
"""

from __future__ import annotations

import io
import json
import os
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from rvb_ai.recordings import FORMAT

TAKE_ID_LEN = 32


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.takes_dir = self.root / "takes"
        self.takes_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.db_path = self.root / "db.json"
        self._lock = threading.Lock()
        self._db = self._read()

    # ----- persistence -----
    def _read(self) -> dict:
        if self.db_path.is_file():
            return json.loads(self.db_path.read_text(encoding="utf-8"))
        return {"custom_phrases": [], "takes": []}

    def _write(self) -> None:
        tmp = self.db_path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self._db, f, indent=1)
        os.replace(tmp, self.db_path)

    def _audio_path(self, take_id: str) -> Path:
        if len(take_id) != TAKE_ID_LEN or not all(c in "0123456789abcdef" for c in take_id):
            raise KeyError(take_id)
        return self.takes_dir / f"{take_id}.wav"

    # ----- phrases added in the app (English only) -----
    def custom_phrases(self) -> list[dict]:
        return list(self._db["custom_phrases"])

    def add_custom_phrase(self, phrase: dict) -> None:
        with self._lock:
            self._db["custom_phrases"].append(phrase)
            self._write()

    def delete_custom_phrase(self, phrase_id: str) -> list[str]:
        """Remove a custom phrase and its takes. Returns the deleted take ids."""
        with self._lock:
            self._db["custom_phrases"] = [p for p in self._db["custom_phrases"] if p["id"] != phrase_id]
        return self.delete_takes(phrase_id=phrase_id)

    # ----- takes -----
    def takes(self) -> list[dict]:
        return list(self._db["takes"])

    def get_take(self, take_id: str) -> dict | None:
        return next((t for t in self._db["takes"] if t["id"] == take_id), None)

    def add_take(self, wav: bytes, phrase_id: str | None, kind: str, speaker: str, note: str = "") -> dict:
        take = {
            "id": uuid.uuid4().hex,
            "phrase_id": phrase_id,
            "kind": kind,
            "speaker": speaker,
            "note": note,
            "created_at": _now(),
        }
        path = self._audio_path(take["id"])
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(wav)
        with self._lock:
            self._db["takes"].append(take)
            self._write()
        return take

    def read_audio(self, take_id: str) -> bytes:
        return self._audio_path(take_id).read_bytes()

    def delete_takes(self, take_id: str | None = None, **filters) -> list[str]:
        """Delete one take by id, or every take matching all given filters (speaker/kind/phrase_id)."""
        with self._lock:
            keep, gone = [], []
            for t in self._db["takes"]:
                hit = t["id"] == take_id if take_id else all(t.get(k) == v for k, v in filters.items())
                (gone if hit else keep).append(t)
            self._db["takes"] = keep
            self._write()
        for t in gone:
            self._audio_path(t["id"]).unlink(missing_ok=True)
        return [t["id"] for t in gone]

    # ----- export for rvb_ai.eval_matcher -----
    def export_zip(self, phrases: list[dict]) -> bytes:
        buf = io.BytesIO()
        takes = []
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for t in self.takes():
                path = self._audio_path(t["id"])
                if not path.is_file():
                    continue
                name = f"takes/{t['id']}.wav"
                z.write(path, f"recordings/{name}")
                takes.append({**t, "file": name})
            manifest = {"format": FORMAT, "exported_at": _now(), "phrases": phrases, "takes": takes}
            z.writestr("recordings/manifest.json", json.dumps(manifest, indent=1))
        return buf.getvalue()
