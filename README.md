# xemas-python

Official Python SDK for the [XemaS](https://xemas.io) on-chain intelligence API.

```bash
pip install xemas-sdk
```

```python
from xemas import Xemas

client = Xemas(api_key="sk-xemas-...")          # or set XEMAS_API_KEY

result = client.entity("0x1f9840a85d5aF5bf1D1762F925BdADdC4201F984", chain_id=1)

result.data                  # the product payload
result.evidence.coverage     # what was actually assessed
result.evidence.confidence   # how strongly
result.meta.model            # which semantic model produced it
```

## Seven products, one shape

| Method | Question it answers |
|---|---|
| `client.contract(address)` | What is this code, and what can it do? |
| `client.entity(address)` | Who is this on-chain actor? |
| `client.behaviour(address)` | How does it act over time? |
| `client.counterparties(address)` | Who does it transact with? |
| `client.portfolio(address)` | What does it hold? |
| `client.fund_flow(address)` | Where did value come from and go? |
| `client.whale(address)` | Size, concentration, market impact |

All take `chain_id=1` by default and return the same envelope.

## Read the evidence, not just the data

Every response carries `evidence` describing **what the platform could and could not establish**:

```python
r = client.contract(address)

if r.evidence.observed_at is None:
    ...   # nothing reported an observation time - not "observed now"
```

This is the point of the API. `data` alone tells you what was found; `evidence` tells you what that
finding is worth. Two deliberate properties the SDK preserves rather than smooths over:

- **Absent is not null.** When the API omits a key (`governance_metadata`, for instance) it means
  *not produced* - it does not assert an empty value. The SDK never substitutes `None`.
- **An unsent header is not a zero.** `client.rate_limit` fields stay `None` when the API did not
  send them, rather than reading as "0 remaining".

## Errors

```python
from xemas import AuthenticationError, RateLimitError, ServerError, TransportError

try:
    client.entity(address)
except RateLimitError as e:
    e.retry_after          # seconds, when the API sent Retry-After
    e.rate_limit.remaining
except AuthenticationError as e:
    e.request_id           # quote this to support - identifies the exact request
except TransportError:
    ...                    # never reached the API; NOT a finding about the address
```

`TransportError` is deliberately separate from API errors: nothing was evaluated, so it must not be
read as evidence about the address you asked about.

**The SDK does not retry.** A retry spends your quota and latency budget, so that decision stays
yours.

## Configuration

```python
Xemas(
    api_key="sk-xemas-...",              # or XEMAS_API_KEY
    base_url="https://api.xemas.io/v1",  # override for testing
    timeout=30.0,
)
```

## How this SDK stays in step with the API

`openapi/v1.json` is exported from the API's **mounted routes** - not transcribed from
documentation - and pins the request surface this release was built against. Paths, methods and
parameters come from there; the response envelope is hand-written, because the API currently
declares no response schemas and generating from an empty schema would produce untyped results.

- Docs: <https://xemas.io/api>
- API status and keys: <https://xemas.io/developer/api-keys>

## Licence

[Apache License 2.0](LICENSE). Permissive and business-friendly, with an explicit patent grant, so
this client can be embedded in proprietary products without constraining them. The XemaS platform
itself is licensed separately - a client library and a platform warrant different terms.
