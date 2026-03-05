"""
AuthMiddleware — validates key + checks credits before any pipeline runs.

Flow:
  Request → check key exists + active → check credits > 0 → run pipeline
                                       → if 0 credits → 402 Payment Required
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.services.key_store import validate_key, deduct_credit, log_usage

PUBLIC_ROUTES = {"/", "/docs", "/openapi.json", "/redoc"}
PUBLIC_PREFIXES = ("/api/v1/auth/",)

# Routes that consume 1 credit per call
CREDIT_ROUTES = ("/api/v1/generate",)


class AuthMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        # ── CORS preflight — always allow ─────────────────────────────────────
        if request.method == "OPTIONS":
            return await call_next(request)

        # ── Public routes — no key needed ─────────────────────────────────────
        path = request.url.path
        if path in PUBLIC_ROUTES or any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)

        # ── Validate key ──────────────────────────────────────────────────────
        api_key = request.headers.get("X-API-Key", "").strip()

        if not api_key:
            return JSONResponse(status_code=401, content={
                "error":   "Missing API key.",
                "message": "Include your key as: X-API-Key: axg_..."
            })

        key_doc = validate_key(api_key)
        if not key_doc:
            return JSONResponse(status_code=401, content={
                "error":   "Invalid or revoked API key.",
                "message": "Generate a new key at POST /api/v1/auth/generate-key"
            })

        # ── Credit check for pipeline routes ──────────────────────────────────
        if any(path.startswith(r) for r in CREDIT_ROUTES):
            if key_doc.get("credits", 0) <= 0:
                return JSONResponse(status_code=402, content={
                    "error":    "Insufficient credits.",
                    "credits":  0,
                    "user_id":  key_doc.get("user_id"),
                    "message":  "Top up credits at POST /api/v1/auth/add-credits"
                })
            # Deduct 1 credit atomically before pipeline runs
            if not deduct_credit(api_key):
                return JSONResponse(status_code=402, content={
                    "error":   "Insufficient credits.",
                    "credits": 0,
                    "message": "Top up credits at POST /api/v1/auth/add-credits"
                })

        # ── Attach key info to request state ──────────────────────────────────
        request.state.api_key  = api_key
        request.state.user_id  = key_doc.get("user_id", "")
        request.state.credits  = key_doc.get("credits", 0)

        # ── Run the route ─────────────────────────────────────────────────────
        response = await call_next(request)

        # ── Log usage after successful response ───────────────────────────────
        if response.status_code < 500:
            log_usage(api_key)

        return response
