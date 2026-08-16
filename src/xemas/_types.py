"""The XemaS v1 response envelope.

Hand-written on purpose, not generated. The exported `/v1` OpenAPI document (see
`openapi/v1.json`) is authoritative for paths, methods and parameters - but it declares no
response schemas, because the API's routes carry no FastAPI `response_model`. Generating types
from it would produce `Any` for every response.

Attaching `response_model` to the live routes would make the spec self-sufficient, but in FastAPI
that is not a documentation change: it becomes a runtime serialization contract that FILTERS the
response, silently dropping any field the model does not declare. That is a production-behaviour
change and is deliberately out of scope here - it belongs in a separate, separately-verified API
programme whose acceptance test proves no keys disappear from representative real responses.

So: OpenAPI owns the request surface, this module owns the envelope, and product payloads stay
permissive rather than pretending the spec describes fields it does not.
"""
from __future__ import annotations

from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Evidence(BaseModel):
    """Why the platform believes what it returned.

    Present on every v1 response. `observed_at` is `None` when no source reported an observation
    time - which is not the same as "observed now", and the SDK never substitutes one.
    """

    model_config = ConfigDict(extra="allow")

    coverage: Dict[str, Any] = {}
    confidence: Dict[str, Any] = {}
    provenance: List[Any] = []
    observed_at: Optional[str] = None


class Meta(BaseModel):
    """Which semantic model produced `data`, and when this response was generated."""

    model_config = ConfigDict(extra="allow", protected_namespaces=())

    model: str
    version: str
    generated_at: str


class Envelope(BaseModel, Generic[T]):
    """`{ data, evidence, meta }` - the shape every v1 product returns.

    `extra="allow"` throughout is deliberate. The API may add keys before this SDK knows about
    them, and a client that silently discarded them would reproduce, on the consumer side, exactly
    the field-loss hazard that keeps `response_model` off the server routes.

    Note what is NOT modelled here: `governance_metadata`. The API omits that key entirely rather
    than sending `null` when there is nothing to report, and that distinction is meaningful -
    absent means "not applicable/not produced", where `null` would assert an empty value. It stays
    reachable via `extra` so presence remains testable with `"governance_metadata" in envelope`.
    """

    model_config = ConfigDict(extra="allow")

    data: T
    evidence: Evidence
    meta: Meta


class RateLimit(BaseModel):
    """Per-key rate-limit state, parsed from `X-RateLimit-*` on every response.

    Every field is optional: these are read from headers, and a header that was not sent must not
    become a number the caller could mistake for a measurement.
    """

    limit: Optional[int] = None
    remaining: Optional[int] = None
    reset: Optional[int] = None

    @classmethod
    def from_headers(cls, headers: Any) -> "RateLimit":
        def _int(name: str) -> Optional[int]:
            raw = headers.get(name)
            if raw is None:
                return None
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None

        return cls(
            limit=_int("X-RateLimit-Limit"),
            remaining=_int("X-RateLimit-Remaining"),
            reset=_int("X-RateLimit-Reset"),
        )
