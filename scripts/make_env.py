"""Create .env from .env.example with a fresh random helper key and a private data folder.

    python scripts/make_env.py           # refuses to overwrite an existing .env
    python scripts/make_env.py --force   # replace it with a new key (the old key stops working)

On macOS the secret is written to .env.nosync and .env is a symlink to it: iCloud Drive does
not sync files named *.nosync, so the key never leaves this computer even when the project
lives in an iCloud-synced Desktop or Documents folder.
"""

from __future__ import annotations

import os
import platform
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = "RohingyaVoiceInterpreter"


def private_data_dir() -> str:
    """A per-user folder that is not synced by iCloud Desktop/Documents or OneDrive by default."""
    system = platform.system()
    if system == "Darwin":
        return f"~/Library/Application Support/{APP}"
    if system == "Windows":
        return str(Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP)
    return str(Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")) / APP)


def main() -> int:
    link = ROOT / ".env"
    target = ROOT / (".env.nosync" if platform.system() == "Darwin" else ".env")
    if (link.exists() or link.is_symlink()) and "--force" not in sys.argv:
        print(".env already exists; leaving it alone (use --force to replace it).")
        return 0
    lines = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith("RVB_ADMIN_TOKEN="):
            line = f"RVB_ADMIN_TOKEN={secrets.token_urlsafe(32)}"
        elif line.startswith("RVB_DATA_DIR="):
            line = f"RVB_DATA_DIR={private_data_dir()}"
        lines.append(line)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    if os.name != "nt":
        os.chmod(target, 0o600)
    if target != link:
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(target.name)
    print(f"Wrote {target.name} (owner-only). Recordings will be stored in {private_data_dir()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
