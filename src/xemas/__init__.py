"""XemaS - on-chain intelligence for developers.

    from xemas import Xemas

    client = Xemas(api_key="sk-xemas-...")
    result = client.entity("0x1f9840a85d5aF5bf1D1762F925BdADdC4201F984")

Seven products, one envelope: `contract`, `entity`, `behaviour`, `counterparties`, `portfolio`,
`fund_flow`, `whale`. Every response carries `evidence` describing what was actually assessed -
read it before drawing conclusions from `data`.

Docs: https://xemas.io/api
"""
from ._client import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, Xemas, __version__
from ._errors import (
    APIStatusError,
    AuthenticationError,
    NotFoundError,
    PermissionError_,
    RateLimitError,
    ServerError,
    TransportError,
    XemasError,
)
from ._types import Envelope, Evidence, Meta, RateLimit

__all__ = [
    "Xemas", "__version__", "DEFAULT_BASE_URL", "DEFAULT_TIMEOUT",
    "Envelope", "Evidence", "Meta", "RateLimit",
    "XemasError", "TransportError", "APIStatusError", "AuthenticationError",
    "PermissionError_", "NotFoundError", "RateLimitError", "ServerError",
]
