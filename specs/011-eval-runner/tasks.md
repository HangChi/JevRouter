# Tasks: Eval Runner and LLM Baseline

## Phase 1: LLM adapter

- [x] T001 Implement `jev_router/clients/llm.py`: frozen `LLMClientConfig` (key, base URL, timeout, max tokens, API version) with `from_env`, `LLMClient.complete(*, model, system, prompt, max_tokens)` over an injectable httpx transport, `LLMCompletion` (text, model, input/output tokens) and the error taxonomy (`LLMClientError` with `category`, plus configuration/transport/http/response variants).
- [x] T002 Unit-test the client against `httpx.MockTransport`: request path, headers, body shape; text and usage parsing; non-2xx, transport failure, invalid JSON and missing-content mapping; config rejection of a blank key, non-HTTPS base URL and non-positive timeout; `from_env` defaults.

## Phase 2: Baseline router and token usage

- [x] T003 Implement `evals/llm_router.py`: candidate set from the registry plus the three control actions, prompt carrying goal/step/history/last result, strict-JSON parsing with brace-balanced extraction, candidate validation, `LLMRouteDecision` (action, reason, model, latency_ms, input/output tokens) and `LLMRouterError`.
- [x] T004 Unit-test the baseline router with a stub client: action parsed from bare and fenced JSON; unknown action, malformed JSON and missing keys raise; latency and tokens recorded; the prompt contains the goal and every candidate.
- [x] T005 Add optional `input_tokens`/`output_tokens` to `RouteDecision`, populated from the provider response usage, and cover the mapping in `tests/test_router.py`.

## Phase 3: Cases

- [x] T006 Implement `evals/cases.py`: strict `EvalCase` model and `load_cases` reading a versioned envelope, refusing an unknown version, duplicate ids, an empty list, a blank/untripped action and an expected action outside the allowed set.
- [x] T007 Write `evals/cases.json` with 50 cases: every registered tool and all three control actions, `requires_confirmation` true exactly for `write_file`/`send_mock_email`, stable kebab-case ids, and a few multi-action allowed sets so allowed-match differs from expected-match.
- [x] T008 Test the loader against the committed file (count, uniqueness, expected-in-allowed, confirmation flags) and against hand-built invalid files (unknown version, duplicate id, empty list, expected outside allowed).

## Phase 4: Runner and metrics

- [x] T009 Implement `evals/registry.py`: the deterministic five-tool registry (search tools with fixed fixtures, `write_file` rooted at a caller-provided temporary directory) so a run is reproducible and offline.
- [x] T010 Implement `evals/runner.py`: `EvalRunner` over injected routers, routing-state construction identical to the Runner's, per-case `CaseOutcome` (action, matched flags, policy outcome, escalation, confirmation, latency, tokens, error, succeeded) and `EvalReport` (run id, mode, created_at, outcomes, metrics); router exceptions become error outcomes.
- [x] T011 Implement `evals/metrics.py`: `summarize` producing per-mode counts and rates, escalation/confirmation counts, latency mean/p50/p95/max, token mean/total, and the cross-mode agreement rate over cases where both routers answered; zeroed metrics for an empty input.
- [x] T012 Unit-test the runner with fake routers: both modes and compare, policy outcomes driving escalation/confirmation, a raising router recorded as an error outcome, `succeeded` false on a confirmation mismatch.
- [x] T013 Unit-test the metrics: exact rate arithmetic, percentile placement, agreement over paired cases only, and the empty input.

## Phase 5: CLI and API delegation

- [x] T014 Implement `evals/cli.py` and `evals/__main__.py`: `--cases`, `--mode jev|llm|compare`, `--jev-model`, `--llm-model`, `--json-out`, `--limit`; credentials resolved from the environment and missing ones failing before any case runs; a stdout summary; non-zero exit when any case errored.
- [x] T015 Add optional LLM delegation to `apps/api`: `Settings.llm_model`/`Settings.llm` from `LLM_MODEL`/`LLM_API_KEY` (both absent by default), an injectable `llm_client` on `TaskService`, an `_LLMDelegate` that asks the model for the pending step's reasoning text, and tests that an unconfigured service still fails closed on delegation while a configured one delegates through a stub client.

## Phase 6: Documentation and checks

- [x] T016 Update `README.md`, `docs/development.md`, `docs/architecture.md`, `docs/security.md` and `.env.example` for the LLM adapter, the eval package, the CLI and the delegation wiring; add `evals` to the mypy invocation.
- [x] T017 Write this spec directory's `data-model.md` and `quickstart.md`, then run ruff, strict mypy over `jev_router apps evals` and the full pytest suite.
- [x] T018 Verify against the real app: boot `apps.api` under uvicorn with a stubbed Jev client and a stubbed LLM client, drive a delegating run through curl, and run the eval CLI in-process against fake routers to confirm the report shape.

## Dependencies

T001 precedes T003/T015. T005 is independent. T006–T008 precede T010. T009–T011 precede T012/T013. T014 needs T010–T013. T016–T018 follow implementation.

## Completion Criteria

All tasks are checked only after implementation and validation. No threshold value changes in this phase, and `evals/{cases,runner,metrics,llm_router,registry}.py` import nothing from `apps/`.
