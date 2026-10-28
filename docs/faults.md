# Fault reference

The current catalog, grouped by category (also printed by `chaos faults`). Each one is selectable
per tool, per endpoint or per model with a `where` selector, and fires according to a `policy`
(`Always`, `Probability(p)`, `OnCall(n)`, `FirstN(n)`).

## Tool

| Fault | What it simulates |
| --- | --- |
| `timeout` | The tool never answers. The real call is NOT executed. |
| `error_status` / `rate_limit` | 500, 429, 401 responses. The real call is NOT executed. |
| `malformed_output` | The call succeeds but the payload is corrupted: truncated or with nulled values. |
| `partial_success` | The side effect HAPPENS but the response is lost. Exposes unsafe retries. |
| `duplicate_delivery` | The call is delivered twice (at-least-once delivery). |
| `stale_data` | Returns a fixed outdated value instead of the real response. |

## Model

| Fault | What it simulates |
| --- | --- |
| `refusal` | The model refuses to answer instead of completing the task. The real call is NOT executed. |
| `format_drift` | The model ignores the requested schema or language, flattening structured output to loose text. |
| `truncation` | The model's output is cut off at the token limit, leaving a half-finished result. |

## Context

| Fault | What it simulates |
| --- | --- |
| `window_overflow` | The context window fills up: older entries fall out, only the most recent fraction survives. |
| `memory_corruption` | An earlier entry in the result is silently altered, as if memory had been corrupted. |

## Security

| Fault | What it simulates |
| --- | --- |
| `indirect_injection` | Instructions hidden in data the agent reads (tool output, web page, email, file). |
| `exfiltration_bait` | Injection that tries to make the agent send data to an attacker URL. |

## Replay

| Fault | What it simulates |
| --- | --- |
| `replay` | Replays a previously recorded trace instead of running the real calls (see `record.py` / `chaos record`). |

This list is maintained by hand; `chaos faults` always reflects the installed version exactly,
including any third-party faults registered under the `agent_chaos.faults` entry point.
