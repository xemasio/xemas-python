"""Typed errors for the XemaS API.

Every error carries the response's `X-Request-Id` when the API sent one. That header is the fastest
route to a specific request in XemaS's logs, so surfacing it turns a support conversation from
"it failed sometimes" into a single identifier.
"""
from __future__ import annotations

from typing import Any, Optional

from ._types import RateLimit


class XemasError(Exception):
    """Base class for every error this SDK raises. Catch this to catch all of them."""

    def __init__(self, message: str, *, request_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.request_id = request_id

    def __str__(self) -> str:
        return f"{self.message} (request_id={self.request_id})" if self.request_id else self.message


class TransportError(XemasError):
    """The request never produced an HTTP response - DNS, TLS, connection or timeout.

    Deliberately distinct from `APIError`: nothing was evaluated, so a caller must not treat this
    as evidence about the address it asked for.
    """


class APIStatusError(XemasError):
    """The API returned a non-2xx response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        detail: Any = None,
        request_id: Optional[str] = None,
        rate_limit: Optional[RateLimit] = None,
    ) -> None:
        super().__init__(message, request_id=request_id)
        self.status_code = status_code
        self.detail = detail
        self.rate_limit = rate_limit


class AuthenticationError(APIStatusError):
    """401 - the key is missing, malformed, revoked or unknown.

    Keys are `sk-xemas-...`; pass one as `Xemas(api_key=...)` or set `XEMAS_API_KEY`.
    """


class PermissionError_(APIStatusError):
    """403 - the key is valid but the plan does not include this product."""


class NotFoundError(APIStatusError):
    """404 - no such endpoint. A valid address with no data returns 200 with empty `data`."""


class RateLimitError(APIStatusError):
    """429 - the per-key window is exhausted.

    `retry_after` is the API's own `Retry-After` in seconds when sent. The SDK does NOT retry on
    your behalf: a retry is a decision about your quota and latency budget, so it stays yours.
    """

    def __init__(self, message: str, *, retry_after: Optional[int] = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ServerError(APIStatusError):
    """5xx - the failure is on the XemaS side. Safe to retry with backoff."""


def error_for_status(
    status_code: int,
    *,
    detail: Any,
    request_id: Optional[str],
    rate_limit: Optional[RateLimit],
    retry_after: Optional[int] = None,
) -> APIStatusError:
    """Map an HTTP status onto the narrowest error type available."""
    common = dict(status_code=status_code, detail=detail, request_id=request_id, rate_limit=rate_limit)
    if status_code == 401:
        return AuthenticationError("Invalid or missing API key", **common)
    if status_code == 403:
        return PermissionError_("This API key's plan does not permit that request", **common)
    if status_code == 404:
        return NotFoundError("No such endpoint", **common)
    if status_code == 429:
        return RateLimitError("Rate limit exceeded for this API key", retry_after=retry_after, **common)
    if status_code >= 500:
        return ServerError(f"XemaS API error (HTTP {status_code})", **common)
    return APIStatusError(f"Unexpected response (HTTP {status_code})", **common)
