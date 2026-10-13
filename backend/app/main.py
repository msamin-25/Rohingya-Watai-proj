"""App factory. Run from backend/:

    uvicorn app.main:factory --factory --reload --port 8000

uvicorn binds to 127.0.0.1 by default, so the app is only reachable from this computer.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .api import router
from .engine import Engine
from .security import SecurityHeaders, content_security_policy, inline_hashes
from .settings import Settings
from .storage import Storage

MISSING_BUILD = """<!doctype html><meta charset="utf-8"><title>Build needed</title>
<p>The frontend is not built yet. Run <code>cd frontend && npm ci && npm run build</code>.</p>"""


def factory(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    # No interactive docs page: it would load scripts from a CDN. The schema stays available.
    app = FastAPI(
        title="Rohingya Voice Interpreter",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.state.settings = settings
    app.state.engine = Engine(Storage(settings.data_dir), settings.seed_path)

    index = settings.frontend_index.read_text(encoding="utf-8") if settings.frontend_index.is_file() else MISSING_BUILD
    scripts, styles = inline_hashes(index)

    app.add_middleware(SecurityHeaders, csp=content_security_policy(scripts, styles))
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)  # blocks DNS rebinding

    @app.get("/", include_in_schema=False)
    def home() -> HTMLResponse:
        return HTMLResponse(index)

    app.include_router(router)
    return app
