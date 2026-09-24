# Tasks: LLM Argument Synthesis

## Phase 1: Tool protocol and input models

- [x] T001 Add `input_model: type[BaseModel]` to the `Tool` protocol in `jev_router/tools/base.py` and declare it on all five tools, reusing the pydantic model each `execute` already validates against (`SearchInput` shared by the two search tools).
- [x] T002 Add `Field(description=...)` to the four input models (`CalculatorInput`, `WriteFileInput`, `MockEmailInput`, `SearchInput`) so the generated schema carries the constraints prose a model needs; keep validation behaviour unchanged.
- [x] T003 Update the three stub tools in `tests/` to declare an input model, and add a test asserting every registered tool declares a model whose fields its `execute` accepts.

## Phase 2: The resolver

- [x] T004 Implement `apps/api/llm.py`: move the delegate handler from `service.py` and add `LLMArgumentResolver` with the prompt builder, the schema renderer (type, required/optional, validity constraints, description) and strict-JSON parsing that raises `ValueError` carrying the failure.
- [x] T005 Unit-test `apps/api/llm.py`: the prompt carries goal, step, history, action, description, risk and every field line; bare and fenced JSON parse; a non-object, a missing key and a non-string value each raise; a provider error carries its category; history is clipped.
- [x] T006 Wire the resolver into `TaskService` next to the delegate, both assembled from the same `llm`/`llm_model` pair and both absent when unconfigured.

## Phase 3: End-to-end and checks

- [x] T007 Test a full run through the HTTP boundary: a route to `calculator` executes with the model's synthesized arguments, the trace records them, and the tool's real output lands in the result.
- [x] T008 Test the failure paths end to end: a provider error and a malformed completion each produce a failed run whose diagnostic names the cause; an unconfigured service still fails the way phase 7 shipped.
- [x] T009 Update `README.md`, `docs/development.md`, `docs/architecture.md` and `docs/security.md` for the resolver, the protocol change and the trust boundary around model-produced arguments.
- [x] T010 Write this spec directory's `data-model.md` and `quickstart.md`, run ruff, strict mypy over `jev_router apps evals` and the full pytest suite, then verify against the real app: boot `apps.api` under uvicorn with stubbed Jev and LLM clients and drive a run that executes a real tool through curl.

## Dependencies

T001 precedes T002/T003. T001–T003 precede T004. T004 precedes T005/T006. T006 precedes T007/T008. T009–T010 follow implementation.

## Completion Criteria

All tasks are checked only after implementation and validation. No change to `Runner`, to any tool's validation behaviour, or to the Policy Engine thresholds, and `jev_router/` still imports nothing from `apps/`.
