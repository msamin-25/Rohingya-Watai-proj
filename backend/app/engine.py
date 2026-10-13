"""Glue between storage and the rvb_ai matcher + safety gate."""

from __future__ import annotations

import re
import threading

import numpy as np

from rvb_ai.audio import AudioError, quality, read_wav
from rvb_ai.features import extract
from rvb_ai.matcher import Matcher, Template
from rvb_ai.phrases import Phrase, load_seed, validate
from rvb_ai.safety import Decision, Thresholds, decide

from .storage import Storage


class Engine:
    def __init__(self, storage: Storage, seed_path, thresholds: Thresholds | None = None):
        self.storage = storage
        self.thresholds = thresholds or Thresholds()
        self.seed = load_seed(seed_path)
        self._lock = threading.Lock()
        self.matcher = Matcher()
        for t in storage.takes():
            if t["kind"] == "teach" and t["phrase_id"] in self.phrases():
                try:
                    x, rate = read_wav(storage.read_audio(t["id"]))
                except (AudioError, OSError):
                    continue
                self.matcher.add(Template(t["phrase_id"], extract(x, rate), t["id"], t["speaker"]))

    # ----- phrases -----
    def phrases(self) -> dict[str, Phrase]:
        out = {p.id: p for p in self.seed}
        for p in self.storage.custom_phrases():
            out[p["id"]] = Phrase(p["id"], p["english"], p["category"], custom=True)
        return out

    def categories(self) -> dict[str, str]:
        return {pid: p.category for pid, p in self.phrases().items()}

    def phrase_list(self) -> list[dict]:
        counts: dict[tuple[str, str], int] = {}
        for t in self.storage.takes():
            key = (t["phrase_id"], t["kind"])
            counts[key] = counts.get(key, 0) + 1
        return [
            {**p.to_dict(), "teach_takes": counts.get((p.id, "teach"), 0), "test_takes": counts.get((p.id, "test"), 0)}
            for p in self.phrases().values()
        ]

    def add_phrase(self, english: str, category: str) -> Phrase:
        base = re.sub(r"[^a-z0-9]+", "_", english.lower()).strip("_")[:40] or "phrase"
        pid, n = f"custom_{base}"[:48], 2
        while pid in self.phrases():
            pid, n = f"custom_{base}"[:44] + f"_{n}", n + 1
        phrase = validate(Phrase(pid, english.strip(), category, custom=True))
        self.storage.add_custom_phrase({"id": phrase.id, "english": phrase.english, "category": phrase.category})
        return phrase

    def delete_phrase(self, phrase_id: str) -> int:
        with self._lock:
            gone = self.storage.delete_custom_phrase(phrase_id)
            for tid in gone:
                self.matcher.remove_take(tid)
        return len(gone)

    # ----- takes -----
    def add_take(self, wav: bytes, phrase_id: str | None, kind: str, speaker: str, note: str) -> dict:
        x, rate = read_wav(wav)
        q = quality(x, rate)
        if q.problem:
            raise AudioError(q.problem)
        feats = extract(x, rate) if kind == "teach" else None
        take = self.storage.add_take(wav, phrase_id, kind, speaker, note)
        if feats is not None:
            with self._lock:
                self.matcher.add(Template(phrase_id, feats, take["id"], speaker))
        return take

    def delete_takes(self, take_id: str | None = None, **filters) -> int:
        with self._lock:
            gone = self.storage.delete_takes(take_id, **filters)
            for tid in gone:
                self.matcher.remove_take(tid)
        return len(gone)

    # ----- interpretation -----
    def interpret(self, wav: bytes) -> dict:
        x, rate = read_wav(wav)
        q = quality(x, rate)
        if q.problem:
            return {"status": q.problem}
        feats: np.ndarray = extract(x, rate)
        with self._lock:
            ranked = self.matcher.rank(feats)
        decision: Decision = decide(ranked, self.categories(), self.thresholds)
        result = {"status": decision.status}
        if decision.status == "match":
            phrase = self.phrases()[decision.phrase_id]
            result.update(phrase_id=phrase.id, english=phrase.english, category=phrase.category)
        elif decision.status == "interpreter_needed":
            result["category"] = decision.category
        return result
