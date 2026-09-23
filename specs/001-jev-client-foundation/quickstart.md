# Quickstart Validation: Jev Client Foundation

## Prerequisites

- Python 3.9 or newer supported by the selected lockfile.
- `uv` installed.
- No live API key is needed for tests.

## Install

From the repository root:

```sh
uv sync --all-groups
```

## Offline validation

```sh
uv run ruff check .
uv run mypy jev_router
uv run pytest
```

Expected result: all tests pass without network access or billable service requests. Mocked transport tests verify all three question types, mixed requests, validation, failures, and credential redaction.

## Optional local usage

Set `JEV_API_KEY` in an ignored local `.env` file or export it in the server environment. The key is never placed in source, client-side code, docs, or test fixtures. Supply the desired model identifier explicitly when making a decision request.

A live service call is deliberately not part of the default quickstart because it may incur cost. Do not use a credential previously exposed in chat; rotate it before any authorized live call.
