"""Configuration from environment variables and the repo-root .env file (never committed)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIN_TOKEN_LEN = 32
PLACEHOLDER = "change-me"


def read_dotenv(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser (comments and blank lines ignored, optional quotes stripped)."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


@dataclass(frozen=True)
class Settings:
    admin_token: str
    data_dir: Path
    allowed_hosts: list[str] = field(default_factory=lambda: ["localhost", "127.0.0.1"])
    max_upload_bytes: int = 2_000_000
    frontend_index: Path = REPO_ROOT / "frontend" / "dist" / "index.html"
    seed_path: Path = REPO_ROOT / "data" / "phrases.seed.json"

    @classmethod
    def load(cls, env_file: Path | None = REPO_ROOT / ".env") -> "Settings":
        env = {**(read_dotenv(env_file) if env_file else {}), **os.environ}
        token = env.get("RVB_ADMIN_TOKEN", "")
        if len(token) < MIN_TOKEN_LEN or PLACEHOLDER in token:
            raise RuntimeError(
                "RVB_ADMIN_TOKEN is missing or too weak. Create .env with `python scripts/make_env.py` "
                f"(it needs at least {MIN_TOKEN_LEN} random characters)."
            )
        data_dir = Path(env.get("RVB_DATA_DIR", "var")).expanduser()
        if not data_dir.is_absolute():
            data_dir = REPO_ROOT / data_dir
        hosts = [h.strip() for h in env.get("RVB_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
        return cls(
            admin_token=token,
            data_dir=data_dir,
            allowed_hosts=hosts,
            max_upload_bytes=int(env.get("RVB_MAX_UPLOAD_BYTES", "2000000")),
        )
