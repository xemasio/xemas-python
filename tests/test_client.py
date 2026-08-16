"""v0.1 contract tests.

These pin the behaviours the SDK promises, using a mock transport rather than the live API - so
they run in CI without a key and cannot be affected by production data changing.

The envelope tests matter most. XemaS's whole differentiator is that a response says what it could
NOT establish, so an SDK that quietly normalised those distinctions away would defeat the product
it wraps. In particular: absent is not null, and an unsent header is not a zero.
"""
from __future__ import annotations

import httpx
import pytest

from xemas import (
    AuthenticationError,
    Envelope,
    RateLimitError,
    ServerError,
    TransportError,
    Xemas,
    XemasError,
)

ADDR = "0x1f9840a85d5aF5bf1D1762F925BdADdC4201F984"

ENVELOPE = {
    "data": {"identity_state": "attributed", "name": "Uniswap"},
    "evidence": {
        "coverage": {"sources_checked": 3},
        "confidence": {"attribution": "high"},
        "provenance": [{"provider": "on-chain", "category": "identity"}],
        "observed_at": "2026-08-16T00:00:00+00:00",
    },
    "meta": {"model": "EntityProfile", "version": "v1", "generated_at": "2026-08-16T00:00:01+00:00"},
}


def _client(handler, **kw) -> Xemas:
    transport = httpx.MockTransport(handler)
    return Xemas(api_key="sk-xemas-test", client=httpx.Client(transport=transport), **kw)


def _ok(payload=ENVELOPE, headers=None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, headers=headers or {})
    return handler


# ── construction ────────────────────────────────────────────────────────────────────────────
class TestConstruction:
    def test_requires_a_key(self, monkeypatch):
        monkeypatch.delenv("XEMAS_API_KEY", raising=False)
        with pytest.raises(XemasError, match="No API key"):
            Xemas()

    def test_reads_the_environment(self, monkeypatch):
        monkeypatch.setenv("XEMAS_API_KEY", "sk-xemas-fromenv")
        assert Xemas().api_key == "sk-xemas-fromenv"

    def test_rejects_a_key_with_the_wrong_prefix(self):
        """Caught locally rather than sent: a wrong-service key would otherwise return a generic
        401 and look like an account problem."""
        with pytest.raises(XemasError, match="does not look like a XemaS key"):
            Xemas(api_key="sk-live-somethingelse")

    def test_base_url_is_configurable_for_testing(self):
        assert _client(_ok(), base_url="http://localhost:8000/v1").base_url == "http://localhost:8000/v1"


# ── the seven products ──────────────────────────────────────────────────────────────────────
class TestSevenProducts:
    PRODUCTS = ["contract", "entity", "behaviour", "counterparties", "portfolio", "fund_flow", "whale"]

    @pytest.mark.parametrize("product", PRODUCTS)
    def test_each_product_calls_its_own_path_and_returns_an_envelope(self, product):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["chain_id"] = request.url.params.get("chain_id")
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json=ENVELOPE)

        result = getattr(_client(handler), product)(ADDR, chain_id=137)
        expected = product.replace("_", "-")            # fund_flow -> /fund-flow
        assert seen["path"] == f"/v1/{expected}/{ADDR}"
        assert seen["chain_id"] == "137"
        assert seen["auth"] == "Bearer sk-xemas-test"
        assert isinstance(result, Envelope)

    def test_all_seven_are_present(self):
        c = _client(_ok())
        for p in self.PRODUCTS:
            assert callable(getattr(c, p)), f"{p} missing from the v0.1 surface"

    def test_chain_id_defaults_to_one(self):
        seen = {}

        def handler(request):
            seen["chain_id"] = request.url.params.get("chain_id")
            return httpx.Response(200, json=ENVELOPE)

        _client(handler).entity(ADDR)
        assert seen["chain_id"] == "1"


# ── the envelope ────────────────────────────────────────────────────────────────────────────
class TestEnvelopeSemantics:
    def test_envelope_is_parsed_into_typed_fields(self):
        r = _client(_ok()).entity(ADDR)
        assert r.data["identity_state"] == "attributed"
        assert r.evidence.coverage["sources_checked"] == 3
        assert r.meta.model == "EntityProfile"

    def test_absent_governance_metadata_stays_absent(self):
        """The API OMITS this key rather than sending null when there is nothing to report.
        Absent means 'not produced'; null would assert an empty value. The SDK must not invent
        one, or it would manufacture certainty the API declined to express."""
        r = _client(_ok()).entity(ADDR)
        dumped = r.model_dump()
        assert "governance_metadata" not in dumped

    def test_present_governance_metadata_is_preserved(self):
        payload = {**ENVELOPE, "governance_metadata": {"reviewed": True}}
        r = _client(_ok(payload)).entity(ADDR)
        assert r.model_dump()["governance_metadata"] == {"reviewed": True}

    def test_unknown_future_keys_are_not_discarded(self):
        """The API may add keys before this SDK knows about them. Dropping them would reproduce,
        on the client side, the field-loss hazard that keeps response_model off the server."""
        payload = {**ENVELOPE, "data": {**ENVELOPE["data"], "brand_new_field": 42}}
        assert _client(_ok(payload)).entity(ADDR).data["brand_new_field"] == 42

    def test_null_observed_at_is_preserved_as_none(self):
        payload = {**ENVELOPE, "evidence": {**ENVELOPE["evidence"], "observed_at": None}}
        assert _client(_ok(payload)).entity(ADDR).evidence.observed_at is None


# ── errors ──────────────────────────────────────────────────────────────────────────────────
class TestErrors:
    def _status(self, code, headers=None, body=None):
        def handler(request):
            return httpx.Response(code, json=body or {"detail": "nope"}, headers=headers or {})
        return handler

    def test_401_raises_authentication_error(self):
        with pytest.raises(AuthenticationError) as e:
            _client(self._status(401, {"X-Request-Id": "req-1"})).entity(ADDR)
        assert e.value.status_code == 401
        assert e.value.request_id == "req-1"

    def test_429_carries_retry_after_and_rate_limit(self):
        headers = {"Retry-After": "60", "X-RateLimit-Limit": "80", "X-RateLimit-Remaining": "0"}
        with pytest.raises(RateLimitError) as e:
            _client(self._status(429, headers)).entity(ADDR)
        assert e.value.retry_after == 60
        assert e.value.rate_limit.remaining == 0

    def test_5xx_raises_server_error(self):
        with pytest.raises(ServerError):
            _client(self._status(503)).entity(ADDR)

    def test_transport_failure_is_distinct_from_an_api_error(self):
        """Nothing was evaluated, so this must not be mistaken for a finding about the address."""
        def handler(request):
            raise httpx.ConnectError("no route to host")
        with pytest.raises(TransportError):
            _client(handler).entity(ADDR)

    def test_the_request_id_is_surfaced_for_support(self):
        with pytest.raises(AuthenticationError) as e:
            _client(self._status(401, {"X-Request-Id": "abc-123"})).entity(ADDR)
        assert "abc-123" in str(e.value)

    def test_no_silent_retry(self):
        """A retry spends the caller's quota and latency budget, so it stays the caller's
        decision. One call must produce exactly one request."""
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(500, json={"detail": "boom"})

        with pytest.raises(ServerError):
            _client(handler).entity(ADDR)
        assert len(calls) == 1


# ── rate-limit metadata ─────────────────────────────────────────────────────────────────────
class TestRateLimitMetadata:
    def test_headers_are_exposed_after_a_successful_call(self):
        c = _client(_ok(headers={"X-RateLimit-Limit": "80", "X-RateLimit-Remaining": "78",
                                 "X-RateLimit-Reset": "1786856936"}))
        c.entity(ADDR)
        assert (c.rate_limit.limit, c.rate_limit.remaining) == (80, 78)

    def test_missing_headers_stay_none_rather_than_zero(self):
        """An unsent header is not a measurement of zero remaining quota."""
        c = _client(_ok())
        c.entity(ADDR)
        assert c.rate_limit.limit is None and c.rate_limit.remaining is None
