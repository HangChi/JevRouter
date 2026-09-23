# Feature Specification: Tool Registry and MVP Tools

**Feature Branch**: `002-tool-registry`
**Status**: Complete

## Goal

Provide application developers a typed, offline-testable registry for a trusted set of tools and the five initial JevRouter tools, without implementing routing or policy orchestration.

## User Stories

### US1 - Register and execute trusted tools

As an application developer, I need to register a finite set of tools with declared risk and call them by name so that routing can later select from an application-controlled allowlist.

Acceptance scenarios:
1. Registering distinct named tools permits lookup and execution; duplicate or unknown names fail clearly.
2. Tool results carry the originating tool name and structured output.
3. Every tool declares `read`, `write`, or `external` risk; the registry itself does not treat model output as authorization.

### US2 - Use offline MVP tools safely

As an application developer, I need deterministic calculator, search, file-write, and mock-email tools so that the router can be developed without live external services.

Acceptance scenarios:
1. Calculator evaluates supported arithmetic and rejects names, calls, unsupported syntax, and excessive expressions.
2. Search tools only query injected local documents/fixtures and bound input and output sizes.
3. File writing stays within a configured root, rejects traversal and symlink escape, enforces a byte limit, and denies overwrites by default.
4. Mock email validates required fields and returns a local simulation without sending a message.

## Requirements

- **FR-001**: Provide a typed tool contract with name, description, risk, and synchronous execution input/result.
- **FR-002**: Registry registration is trusted application configuration and rejects duplicate/invalid names.
- **FR-003**: Implement `calculator`, `knowledge_search`, `web_search`, `write_file`, and `send_mock_email`.
- **FR-004**: Calculator MUST use a strict arithmetic AST allowlist; it MUST NOT evaluate arbitrary Python code.
- **FR-005**: Search tools MUST use injected fixtures/data and MUST NOT perform network access.
- **FR-006**: File writes MUST enforce a configured root, relative paths, size limits, symlink containment, and no-overwrite-by-default behavior.
- **FR-007**: Mock email MUST NOT send network requests or connect to email services.
- **FR-008**: Tests MUST be deterministic, offline, and cover success and boundary/error cases.
- **FR-009**: Router, policy, runner, verifier, API, dashboard, persistence, and live service integrations are out of scope.

## Success Criteria

- All five tools are constructible and return structured `ToolResult` values.
- Registry tests demonstrate trusted registration, duplicate rejection, and unknown tool handling.
- Safety boundary tests pass for calculator, search, file writing, and mock email.
- Complete test, lint, and static type suites pass without network access.
