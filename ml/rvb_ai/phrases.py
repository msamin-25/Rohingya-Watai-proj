"""Load the starter phrases (English only) from data/phrases.seed.json."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .safety import CATEGORIES, SENSITIVE

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = REPO_ROOT / "data" / "phrases.seed.json"
ID_RE = re.compile(r"^[a-z0-9_]{1,48}$")


@dataclass(frozen=True)
class Phrase:
    id: str
    english: str
    category: str
    custom: bool = False

    @property
    def sensitive(self) -> bool:
        return self.category in SENSITIVE

    def to_dict(self) -> dict:
        return {**asdict(self), "sensitive": self.sensitive}


def validate(p: Phrase) -> Phrase:
    if not ID_RE.match(p.id):
        raise ValueError(f"bad phrase id: {p.id!r}")
    if p.category not in CATEGORIES:
        raise ValueError(f"bad category for {p.id}: {p.category!r}")
    if not p.english.strip() or len(p.english) > 120:
        raise ValueError(f"bad English text for {p.id}")
    return p


def load_seed(path: Path = SEED_PATH) -> list[Phrase]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    phrases = [validate(Phrase(p["id"], p["english"], p["category"])) for p in data["phrases"]]
    ids = [p.id for p in phrases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate phrase ids in seed file")
    return phrases
