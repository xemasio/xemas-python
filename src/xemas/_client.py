"""The XemaS client - seven products, one shape."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

from ._errors import TransportError, XemasError, error_for_status
from ._types import Envelope, RateLimit

DEFAULT_BASE_URL = "https://api.xemas.io/v1"
DEFAULT_TIMEOUT = 30.0
KEY_PREFIX = "sk-xemas-"

__version__ = "0.1.0"


class Xemas:
    """Read access to XemaS on-chain intelligence.

        from xemas import Xemas

        client = Xemas(api_key="sk-xemas-...")
        result = client.entity("0x1f9840a85d5aF5bf1D1762F925BdADdC4201F984", chain_id=1)

        result.data                 # the product payload
        result.evidence.coverage    # what was actually assessed
        result.meta.model           # which semantic model produced it

    All seven products share this signature, and all return the same `{data, evidence, meta}`
    envelope. `evidence` is not decoration: it states what the platform could and could not
    establish, and a caller drawing conclusions from `data` alone is discarding that.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        client: Optional[httpx.Client] = None,
    ) -> None:
        key = api_key or os.environ.get("XEMAS_API_KEY")
        if not key:
            raise XemasError(
                "No API key. Pass Xemas(api_key='sk-xemas-...') or set XEMAS_API_KEY. "
                "Create a key at https://xemas.io/developer/api-keys"
            )
        if not key.startswith(KEY_PREFIX):
            # Fail here rather than sending it: a mistyped or wrong-service key would otherwise
            # come back as a generic 401 and look like an account problem.
            raise XemasError(f"API key does not look like a XemaS key (expected a {KEY_PREFIX}... prefix)")

        self.api_key = key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None
        #: Rate-limit state from the most recent response, or None before the first call.
        self.rate_limit: Optional[RateLimit] = None

    # ── the seven stable products ───────────────────────────────────────────────────────────
    def contract(self, address: str, *, chain_id: int = 1) -> Envelope[Dict[str, Any]]:
        """Contract intelligence: what is this code, and what can it do?"""
        return self._get("contract", address, chain_id)

    def entity(self, address: str, *, chain_id: int = 1) -> Envelope[Dict[str, Any]]:
        """Identity intelligence: who is this on-chain actor?"""
        return self._get("entity", address, chain_id)

    def behaviour(self, address: str, *, chain_id: int = 1) -> Envelope[Dict[str, Any]]:
        """Behavioural intelligence: how does this address act over time?"""
        return self._get("behaviour", address, chain_id)

    def counterparties(self, address: str, *, chain_id: int = 1) -> Envelope[Dict[str, Any]]:
        """Counterparty intelligence: who does it transact with?"""
        return self._get("counterparties", address, chain_id)

    def portfolio(self, address: str, *, chain_id: int = 1) -> Envelope[Dict[str, Any]]:
        """Portfolio intelligence: what does it hold?"""
        return self._get("portfolio", address, chain_id)

    def fund_flow(self, address: str, *, chain_id: int = 1) -> Envelope[Dict[str, Any]]:
        """Fund-flow intelligence: where did value come from and go?"""
        return self._get("fund-flow", address, chain_id)

    def whale(self, address: str, *, chain_id: int = 1) -> Envelope[Dict[str, Any]]:
        """Whale intelligence: size, concentration and market impact."""
        return self._get("whale", address, chain_id)

    # ── auxiliary ───────────────────────────────────────────────────────────────────────────
    def health(self) -> Dict[str, Any]:
        """Liveness check. Requires a valid key, and is not enveloped."""
        return self._request("GET", "/health")

    def entity_history(self, address: str, *, chain_id: int = 1) -> Envelope[Dict[str, Any]]:
        """Identity changes over time. Auxiliary - not one of the seven products."""
        return Envelope[Dict[str, Any]].model_validate(
            self._request("GET", f"/entity/{address}/history", params={"chain_id": chain_id})
        )

    # ── transport ───────────────────────────────────────────────────────────────────────────
    def _get(self, product: str, address: str, chain_id: int) -> Envelope[Dict[str, Any]]:
        if not address or not isinstance(address, str):
            raise XemasError("address must be a non-empty string")
        payload = self._request("GET", f"/{product}/{address}", params={"chain_id": chain_id})
        return Envelope[Dict[str, Any]].model_validate(payload)

    def _request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": f"xemas-python/{__version__}",
        }
        try:
            resp = self._client.request(method, url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            raise TransportError(f"Request to {url} timed out after {self.timeout}s") from exc
        except httpx.HTTPError as exc:
            raise TransportError(f"Could not reach {url}: {exc}") from exc

        # Recorded even on failure: the remaining quota is exactly what a caller needs after a 429.
        self.rate_limit = RateLimit.from_headers(resp.headers)
        request_id = resp.headers.get("X-Request-Id")

        if resp.is_success:
            try:
                return resp.json()
            except ValueError as exc:
                raise XemasError(
                    f"API returned non-JSON on {resp.status_code}", request_id=request_id
                ) from exc

        detail: Any = None
        try:
            body = resp.json()
            detail = body.get("detail", body) if isinstance(body, dict) else body
        except ValueError:
            detail = resp.text or None

        retry_after: Optional[int] = None
        if (raw := resp.headers.get("Retry-After")) is not None:
            try:
                retry_after = int(raw)
            except (TypeError, ValueError):
                retry_after = None

        raise error_for_status(
            resp.status_code,
            detail=detail,
            request_id=request_id,
            rate_limit=self.rate_limit,
            retry_after=retry_after,
        )

    # ── lifecycle ───────────────────────────────────────────────────────────────────────────
    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "Xemas":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
