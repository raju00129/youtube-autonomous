"""Require portal access key on all API routes (header, cookie, or GET query)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings

COOKIE_NAME = "ragam_portal_key"
HEADER_NAME = "x-portal-key"
QUERY_NAME = "portal_key"

# Public paths (no portal key). YouTube OAuth callback is a browser redirect from Google.
PUBLIC_PREFIXES = (
    "/health",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/portal/unlock",
    "/api/v1/youtube/callback",
)


class PortalAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if request.method == "OPTIONS":
            return await call_next(request)
        if any(path == p or path.startswith(p + "/") for p in PUBLIC_PREFIXES) or path in PUBLIC_PREFIXES:
            return await call_next(request)

        settings = get_settings()
        expected = (settings.portal_access_key or "").strip()
        if not expected:
            return await call_next(request)

        provided = (
            (request.headers.get(HEADER_NAME) or "").strip()
            or (request.cookies.get(COOKIE_NAME) or "").strip()
            or (request.query_params.get(QUERY_NAME) or "").strip()
        )
        if provided != expected:
            return JSONResponse(
                status_code=401,
                content={"detail": "Portal access key required"},
            )
        return await call_next(request)
