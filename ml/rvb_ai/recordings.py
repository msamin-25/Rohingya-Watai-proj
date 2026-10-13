"""Read an exported recordings folder: manifest.json + takes/*.wav (format rvb-recordings/1)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .audio import read_wav
from .features import extract

FORMAT = "rvb-recordings/1"


@dataclass
class Take:
    id: str
    phrase_id: str | None  # None = a phrase that was never taught
    kind: str  # "teach" | "test"
    speaker: str
    file: str
    note: str = ""
    features: np.ndarray | None = None


@dataclass
class Recordings:
    phrases: dict[str, dict]  # id -> {"english", "category", ...}
    takes: list[Take]


def find_root(path: Path) -> Path:
    """Accept either the folder with manifest.json or a parent folder containing it once."""
    path = Path(path).expanduser()
    if (path / "manifest.json").is_file():
        return path
    found = sorted(path.glob("*/manifest.json"))
    if len(found) == 1:
        return found[0].parent
    raise FileNotFoundError(f"No manifest.json found in {path} (unzip the export first).")


def load(path: Path, with_features: bool = True) -> Recordings:
    root = find_root(path).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != FORMAT:
        raise ValueError(f"Unsupported manifest format: {manifest.get('format')!r}")
    phrases = {p["id"]: p for p in manifest["phrases"]}
    takes = []
    for t in manifest["takes"]:
        file = (root / t["file"]).resolve()
        if root not in file.parents:  # never read outside the export folder
            raise ValueError(f"Unsafe file path in manifest: {t['file']!r}")
        take = Take(t["id"], t.get("phrase_id"), t["kind"], t.get("speaker", ""), str(file), t.get("note", ""))
        if with_features:
            x, rate = read_wav(file.read_bytes())
            take.features = extract(x, rate)
        takes.append(take)
    return Recordings(phrases, takes)
