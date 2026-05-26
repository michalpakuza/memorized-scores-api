import secrets
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from app.config import settings


WINDOW_SECONDS = 60
MAX_REQUESTS_PER_WINDOW = 120
_requests: dict[str, deque[float]] = defaultdict(deque)


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


def simple_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = _requests[client_ip]

    while bucket and bucket[0] <= now - WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= MAX_REQUESTS_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
        )

    bucket.append(now)
