# POST /v1/systemone

## Status

Verified against the TypeSafe HTTP API reference on 2026-09-23. This contract covers only documented request and typed decision response fields. Undocumented fields are not inferred.

## Request

- Method/path: `POST /v1/systemone`
- Authentication: `Authorization: Bearer <API_KEY>`
- Content type: `application/json`
- JSON object:
  - `state`: string, object, or array.
  - `model`: caller-selected string identifier.
  - `questions`: non-empty object keyed by question name.
- Each question has `type` and `instructions`; instructions may be string, object, or array.
- `noul`: optional criteria describing true/false.
- `choice`: criteria is a mapping of at most 255 candidate identifiers to descriptions.
- `score`: criteria is an ordered array of 2–10 scale labels.

## Response

- JSON object contains `model`, `answers`, and `usage` with input/output token counts.
- `answers` is keyed by submitted question name.
- Noul answer: `type` and `noul` probability in `[0, 1]`.
- Choice answer: `type`, `choice`, `probabilities`, and `confidence`; probability distribution follows the provider's documented normalization rule.
- Score answer: `type`, numeric `score`, `legend`, `probabilities`, and `confidence`; score may be between legend levels and probabilities follow the documented normalization rule.
- Answer type must match the submitted question type.

## Errors and client handling

TypeSafe documents authentication/validation, rate-limit, and service-capacity status codes including 401, 422, 429, and 529. The adapter exposes sanitized typed HTTP failures and does not retry automatically. It does not expose authorization data or raw response content.

## Out of scope

This contract does not define `GET /v1/models`; that endpoint and response schema remain unverified and must not be guessed.
