# Implementation Plan: Eval Runner and LLM Baseline

## Design Decisions

### 1. The LLM adapter lives in the core package, next to the Jev adapter

`jev_router/clients/llm.py` mirrors `clients/jev.py`: frozen config validated at construction, `from_env`, an error taxonomy with a stable `category`, and one async method over an injectable `httpx` transport. The provider shape is the Anthropic Messages API (`POST /v1/messages`, `x-api-key` + `anthropic-version`), which keeps the dependency list at httpx and makes the base URL the only thing a different gateway would change.

The core package still contains no agent logic that calls an LLM on its own; the adapter exists so the API's delegate handler and the eval baseline share one tested client.

### 2. The baseline router is eval infrastructure, not a product router

`evals/llm_router.py` builds the same candidate set as `jev_router.Router` (registered tools plus the three control actions) from the same routing state, and demands a strict JSON object `{"action": ..., "reason": ...}`. It returns `LLMRouteDecision` — action, reason, model, latency, tokens — and deliberately carries no probabilities: an LLM baseline has none, and the comparison table must not pretend otherwise.

Parsing is defensive because the provider is not guaranteed to obey: the whole text is tried as JSON first, then the first brace-balanced object is extracted, then the action is checked against the candidate set. Every failure path raises `LLMRouterError`, which the runner converts into an error outcome.

### 3. Cases are data, validated at the boundary

`EvalCase` is a strict pydantic model (`extra="forbid"`): `id`, `goal`, `expected_action`, `allowed_actions`, `requires_confirmation`, optional `context` and `notes`. The loader reads a versioned envelope `{"version": 1, "cases": [...]}`, refuses an unknown version, and enforces the cross-field rules the schema cannot express: unique ids, non-empty list, `expected_action ∈ allowed_actions`, and trimmed action names.

The committed `cases.json` holds 53 cases across all five tools and the three control actions, with `requires_confirmation` true exactly for the `write`/`external` risk tools — the same rule the Runner enforces at execution time, so the metric measures whether the Policy Engine reaches that conclusion on its own.

### 4. The runner is a pure orchestration over injected routers

`EvalRunner` takes a Jev `Router` (or the pieces to build one), an optional baseline `LLMRouter`, a `ToolRegistry` and a `PolicyEngine`. Per case it builds the same routing state the Runner builds (`goal`, `step`, `context`, `history`, `last_result`), routes once, evaluates the policy, and records one `CaseOutcome` per mode. Latency is wall-clock around the route call; tokens come from `RouteDecision` (Jev) or `LLMRouteDecision` (baseline).

A router raising is caught and recorded as an error outcome, so one bad case cannot abort the run — the same fail-visible philosophy as the trace sink.

`succeeded` is deliberately stricter than "the action was acceptable": it also requires `confirmation_requested == requires_confirmation`. That is the signal the thresholds need calibration against.

### 5. Metrics are pure functions

`metrics.summarize(outcomes)` returns `ModeMetrics` per mode plus `ComparisonMetrics` with the agreement rate over the cases where both routers produced an action. Latency percentiles use the nearest-rank method (documented in the module); tokens report mean and total. An empty input yields zeroed metrics.

### 6. API delegation becomes optional, not newly mandatory

`Settings` gains `llm_model: str | None` and `llm: LLMClientConfig | None`, both `None` unless `LLM_API_KEY` is set (in which case `LLM_MODEL` becomes required). `TaskService` accepts an injectable `llm_client`; when configured it builds an `_LLMDelegate` that asks the model for the reasoning/answer text the pending step needs, and the Runner records it as the `delegate_to_llm` step result. Unconfigured deployments keep phase 7's fail-closed behaviour exactly: the run stops with `failed` and the documented diagnostic.

## File Layout

```text
jev_router/clients/llm.py     # LLMClientConfig, LLMClient, LLMCompletion, error taxonomy
jev_router/router.py          # + input_tokens/output_tokens on RouteDecision
evals/__init__.py
evals/__main__.py             # python -m evals
evals/cases.py                # EvalCase, load_cases, CaseFileError
evals/cases.json              # 50 versioned cases
evals/registry.py             # deterministic eval registry (same five tools)
evals/llm_router.py           # LLMRouter, LLMRouteDecision, LLMRouterError
evals/runner.py               # EvalRunner, CaseOutcome, EvalReport
evals/metrics.py              # ModeMetrics, ComparisonMetrics, summarize
evals/cli.py                  # argparse CLI
tests/test_llm_client.py
tests/test_llm_router.py
tests/test_eval_cases.py
tests/test_eval_runner.py
tests/test_eval_metrics.py
```

## Testing Strategy

- Client and baseline router: `httpx.MockTransport` doubles, no network, no credentials, no billable requests — the same rule as every other test in the repo.
- Runner and metrics: in-process fake routers implementing the same call shape, so policy evaluation, error capture and aggregation are exercised deterministically.
- `cases.json` is validated by a test, so the committed file cannot drift from the loader's rules.
- `tests/test_router.py` gains the token-usage mapping.

## Risks

- **Prompt drift**: the baseline sees a hand-built prompt, so "like-for-like" means the same inputs, not the same encoding. Accepted; the report records the model ids used.
- **Anthropic-specific shape**: a different provider means a different client, not a config change. Accepted for MVP; the adapter boundary is where that swap happens.
- **Latency noise**: single-run wall-clock on a shared machine is noisy. Accepted for MVP; the report keeps raw per-case latencies so a future phase can do repeated runs.
