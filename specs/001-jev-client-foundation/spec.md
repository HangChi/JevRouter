# Feature Specification: Jev Client Foundation

**Feature Branch**: `jev-client-foundation`  
**Created**: 2026-09-23  
**Status**: Complete

## User Scenarios & Testing

### User Story 1 - Submit typed decision questions (Priority: P1)

As an application developer, I need to submit a shared state with one or more supported typed questions and receive their structured answers so that downstream application policy can make deterministic choices.

**Why this priority**: This is the Jev client’s primary decision capability and supports the project's later router without implementing it now.

**Independent Test**: Mock the service boundary and verify serialization and parsing for `noul`, `choice`, and `score`, including mixed question types in a single request.

**Acceptance Scenarios**:
1. **Given** valid shared state and one valid question, **When** the client submits a decision request, **Then** the documented request shape is sent and its typed answer is returned.
2. **Given** valid questions of all supported types, **When** submitted together, **Then** each response is associated with its question and preserves documented confidence/probability information.
3. **Given** an unsupported or invalid question, **When** submitted, **Then** validation rejects it before sending a network request.
4. **Given** a response missing required fields, containing invalid probabilities, or inconsistent with the question type, **When** parsed, **Then** the client reports a response-validation error rather than fabricating a decision.
5. **Given** an HTTP error, timeout, or unavailable service, **When** a decision is requested, **Then** the client returns a typed failure and does not silently retry a potentially billable request.

### User Story 2 - Configure and operate the client safely (Priority: P2)

As an operator, I need to configure the service endpoint, credential, and timeouts outside source code so that the client can run in local and deployed environments without leaking secrets.

**Independent Test**: Instantiate configuration with valid and invalid values, and verify headers and exception/log output never reveal the credential.

**Acceptance Scenarios**:
1. **Given** valid configuration, **When** the client is created, **Then** it uses the configured endpoint and finite connection/read timeouts.
2. **Given** missing or invalid required configuration, **When** configuration is validated, **Then** startup fails with a clear message that does not contain secret values.
3. **Given** any service response or exception, **When** it is surfaced to callers or logs, **Then** authorization secrets are absent.

## Edge Cases

- Empty state, non-JSON-compatible state values, no questions, excessive question count, empty choice options, and duplicate question names.
- Choice responses whose selected value is not among the submitted options.
- Probability values outside [0, 1], non-finite numbers, missing probability maps, and confidence inconsistent with the provider schema.
- Score questions with no criteria or response scores outside the documented scale.
- Unexpected content type, invalid JSON, oversized response, rate limiting, server errors, and cancellation.
- Caller-supplied endpoint with trailing slash or path prefix; ensure endpoint joining does not change configured base path unexpectedly.

## Requirements

### Functional Requirements

- **FR-001**: The client MUST support the documented `POST /v1/systemone` decision operation; model discovery is outside this feature's scope.
- **FR-002**: The client MUST support submitting a shared JSON-compatible state and named questions of types `noul`, `choice`, and `score`.
- **FR-003**: The client MUST allow multiple supported question types in one request and associate each validated answer with its question name.
- **FR-004**: The client MUST validate request question definitions before network transmission.
- **FR-005**: The client MUST validate service responses against the selected question type and preserve documented probability and confidence data.
- **FR-006**: The client MUST distinguish configuration, transport/timeout, HTTP, JSON decoding, and schema validation failures using typed errors.
- **FR-007**: The client MUST apply finite configurable timeouts and MUST NOT automatically retry decision requests by default.
- **FR-008**: The client MUST keep authentication credentials out of returned data, logs, and exception messages.
- **FR-009**: Model selection MUST be supplied by the caller or derived from an explicit discovery result; the client MUST NOT permanently hard-code an account-specific model identifier.
- **FR-010**: Tests MUST exercise all supported question types and error classes using a mocked transport, without requiring live credentials.
- **FR-011**: The scope MUST be limited to the reusable Jev service client, its configuration, typed request/response models, tests, and usage documentation; router, tools, runner, verifier, API, dashboard, and persistence are excluded.

### Key Entities

- **DecisionRequest**: Selected model, shared state, and named question definitions.
- **QuestionDefinition**: A question name, supported type, instructions, and type-specific criteria/options.
- **DecisionResponse**: Validated per-question typed answer and provider-supplied probability/confidence metadata.
- **JevClientConfig**: Service base URL, credential, and finite timeout configuration.
- **JevClientError**: Sanitized typed failure category with safe diagnostic context.

## Success Criteria

- **SC-001**: All three supported question types can be represented and validated before a request is sent.
- **SC-002**: A mixed-question request round-trips through mocked service responses with answers correctly associated to 100% of question names.
- **SC-003**: Every defined configuration, transport, HTTP, decoding, and schema failure has a deterministic typed error and a passing automated test.
- **SC-004**: The complete test suite runs without network access, service credentials, or billable requests.
- **SC-005**: No test, captured log, returned error, or documentation example contains a real credential.

## Assumptions

- The first implementation is a Python library module used by the planned Python agent core.
- The official service contract is authoritative. Product-design examples in `doc.md` illustrate intended usage but are not treated as proof of exact wire schemas.
- The client will use asynchronous HTTP and dependency injection for transport, enabling deterministic tests.
- Safe defaults include finite timeouts, no automatic retries for decisions, and credential redaction.
- Endpoint base URL and credential names will be documented as configuration inputs; real values remain operator-provided.
