# Security & privacy

This app handles **private voice recordings** of vulnerable people. The MVP is designed to run on
one computer, for one helper, on `localhost`.

## What protects what

| Risk | Protection |
|---|---|
| Someone on the network reaches the app | uvicorn binds to `127.0.0.1` only (its default). Do not pass `--host 0.0.0.0`. |
| A malicious website talks to `localhost:8000` (CSRF) | Teaching, deleting and exporting need the helper key in a custom `X-RVB-Key` header; no CORS is enabled, so other sites cannot send it. |
| DNS rebinding | `TrustedHostMiddleware` only answers to `localhost` / `127.0.0.1`. |
| Script injection (XSS) | All server text is inserted with `textContent`. A strict Content-Security-Policy allows only the exact hashed inline script and style (`default-src 'none'`). |
| Clickjacking, sniffing, referrers | `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`. |
| Weak or leaked helper key | The server refuses to start without a 32+ character random key. `scripts/make_env.py` generates one; `.env` is created owner-only (`0600`) and git-ignored. Keys are compared in constant time. |
| Oversized or malformed uploads | Upload limit (default 2 MB), WAV-only decoder, 15 s maximum, sample-rate checks. |
| Path traversal | Take ids are server-generated 32-hex UUIDs and are validated; the eval tool refuses manifest paths outside the export folder. |
| Recordings leaking | Stored outside the repo in `RVB_DATA_DIR` (`0700` folder, `0600` files). Audio sent to **Speak** is never stored. `.gitignore` and CI block `.env`, `var/`, `*.wav`, `*.m4a`, `*.zip`. No analytics, no external requests; English speech uses the browser's own voice. |
| Cloud sync | `make_env.py` puts recordings in a folder that iCloud Desktop/Documents and OneDrive do not sync. The macOS venv lives in `.venv.nosync`. |
| Supply chain | Few dependencies; exact npm versions; `ignore-scripts=true`; `pip-audit` and `npm audit` in CI; CI uses read-only permissions. |

## Before using it beyond localhost

This MVP is **not** ready to be exposed on a network. That would need real user accounts, HTTPS,
rate limiting, audit logs, encryption at rest, a data-retention policy and informed consent.

## Reporting

Please report issues privately to the maintainer rather than in a public issue.
