"""Small per-process rate limiter for authentication endpoints."""

import asyncio
import math
import time
from collections import defaultdict, deque
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

AUTH_LIMITS: dict[str, tuple[int, int]] = {
    "/api/v1/auth/register": (5, 60),
    "/api/v1/auth/login": (10, 60),
    "/api/v1/auth/refresh": (20, 60),
}


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: Callable,
        *,
        limits: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        super().__init__(app)
        self._limits = limits or AUTH_LIMITS
        self._requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        if hasattr(app, "state"):
            app.state.auth_rate_limiter = self

    def reset(self) -> None:
        self._requests.clear()

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        limit_config = self._limits.get(request.url.path)
        if request.method != "POST" or limit_config is None:
            return await call_next(request)

        limit, window_seconds = limit_config
        client_host = request.client.host if request.client else "unknown"
        key = (client_host, request.url.path)
        now = time.monotonic()
        async with self._lock:
            is_new_key = key not in self._requests
            cutoff = now - window_seconds
            request_times = self._requests.get(key, deque())
            while request_times and request_times[0] <= cutoff:
                request_times.popleft()
            if len(request_times) >= limit:
                retry_after = max(1, math.ceil(request_times[0] + window_seconds - now))
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many authentication attempts. Try again later."},
                    headers={"Retry-After": str(retry_after)},
                )
            if is_new_key and len(self._requests) >= 10_000:
                for stale_key in [
                    candidate
                    for candidate, timestamps in self._requests.items()
                    if not timestamps
                    or timestamps[-1]
                    <= now - self._limits.get(candidate[1], (0, 0))[1]
                ]:
                    self._requests.pop(stale_key, None)
                if len(self._requests) >= 10_000:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many authentication attempts. Try again later."},
                        headers={"Retry-After": str(window_seconds)},
                    )
            if is_new_key:
                self._requests[key] = request_times
            request_times.append(now)

        return await call_next(request)
