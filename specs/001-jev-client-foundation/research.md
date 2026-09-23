# Research: Jev Client Foundation

## Provider contract

- Decision: Implement only `POST /v1/systemone` using fields and response structures documented by TypeSafe; model discovery is outside this feature's scope.
- Rationale: This feature is limited to the documented decision endpoint and its typed question/answer schemas.
- Alternatives considered: Adding model discovery to this feature was rejected to keep its scope focused on decision requests.

## Decision request behavior

- Decision: Require callers to provide a model identifier, submit all named questions in one request, use a finite timeout, and do not automatically retry decision requests.
- Rationale: Matches the official endpoint contract and feature requirement to avoid unexpected billable duplicate decisions.
- Alternatives considered: Automatic exponential retry based on provider guidance was rejected for the decision operation because the feature explicitly disallows default automatic retries.

## Typed question and answer validation

- Decision: Model `noul`, `choice`, and `score` as explicit request/response variants, validate question-specific criteria and answer fields at the HTTP boundary, and preserve provider probability/confidence data where documented.
- Rationale: Downstream policy must consume structured, validated decisions rather than untrusted raw JSON.
- Alternatives considered: Returning raw dictionaries was rejected because it shifts provider-schema validation into callers.

## Transport and test strategy

- Decision: Use async HTTPX with an injectable transport and offline pytest coverage; do not perform live/billable calls in ordinary tests.
- Rationale: Fits the repository's adapter boundary and allows deterministic request/response and failure tests.
- Alternatives considered: Calling the live service for integration tests was rejected due to cost, secret handling, and contract uncertainty.

## Speckit setup

- Decision: Maintain the requested feature artifacts manually under the existing feature directory; do not invoke setup scripts that are absent from this repository.
- Rationale: There is no `.specify/` project directory or setup script, despite the installed skill's compatibility requirement.
- Alternatives considered: Fabricating generated setup metadata was rejected.
