"""Helper-key check and HTTP security headers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re

from fastapi import Header, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

KEY_HEADER = "X-RVB-Key"


def require_admin(request: Request, x_rvb_key: str | None = Header(default=None, alias=KEY_HEADER)) -> None:
    """Teaching, deleting and exporting need the helper key from .env.

    It is sent in a custom header, which browsers will not attach to cross-site requests
    without a CORS preflight (and this app allows no cross-origin requests), so it also stops CSRF.
    """
    expected = request.app.state.settings.admin_token
    if not x_rvb_key or not hmac.compare_digest(x_rvb_key.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "A valid helper key is required.")


def inline_hashes(html: str) -> tuple[list[str], list[str]]:
    """CSP sha256 sources for every inline <script> and <style> block in the page."""

    def digest(body: str) -> str:
        return "'sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() + "'"

    scripts = [digest(m) for m in re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.S)]
    styles = [digest(m) for m in re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.S)]
    return scripts, styles


def content_security_policy(script_hashes: list[str], style_hashes: list[str]) -> str:
    return "; ".join(
        [
            "default-src 'none'",
            "script-src " + (" ".join(script_hashes) or "'none'"),
            "style-src " + (" ".join(style_hashes) or "'none'"),
            "connect-src 'self'",
            "img-src 'self' data:",
            "media-src 'self' blob:",
            "base-uri 'none'",
            "form-action 'none'",
            "frame-ancestors 'none'",
        ]
    )


class SecurityHeaders(BaseHTTPMiddleware):
    def __init__(self, app, csp: str):
        super().__init__(app)
        self.csp = csp

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("Content-Security-Policy", self.csp)
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        h["Cross-Origin-Resource-Policy"] = "same-origin"
        h["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=(), payment=()"
        if request.url.path.startswith("/api/"):
            h["Cache-Control"] = "no-store"
        return response
