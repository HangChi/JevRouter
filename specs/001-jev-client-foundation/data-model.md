# Data Model: Jev Client Foundation

## JevClientConfig

- `base_url`: absolute service URL, defaulting to the documented TypeSafe API origin; must be HTTPS outside explicitly controlled tests.
- `api_key`: required secret supplied by environment/configuration; excluded from representation and errors.
- `timeout_seconds`: finite positive total request timeout.

## QuestionDefinition

A named question mapping to one supported variant:

- `NoulQuestion`: `type="noul"`, required instructions (string/object/array), optional criteria describing true/false.
- `ChoiceQuestion`: `type="choice"`, required instructions and criteria mapping candidate identifiers to descriptions; criteria contains 1–255 candidates.
- `ScoreQuestion`: `type="score"`, required instructions and ordered criteria with 2–10 scale labels.

Question names map to question definitions in `DecisionRequest.questions`; request validation rejects empty question sets and unsupported definitions before network I/O.

## DecisionRequest

- `model`: caller-supplied provider model identifier; not hard-coded to an account-specific value.
- `state`: JSON-compatible string, object, or array.
- `questions`: non-empty mapping from question names to typed question definitions.

## Answer variants

- `NoulAnswer`: type discriminator and `noul` probability in `[0, 1]`; no independent confidence field is assumed.
- `ChoiceAnswer`: type discriminator, selected choice, normalized candidate probabilities, and confidence; selected choice must be among submitted candidates.
- `ScoreAnswer`: type discriminator, numeric score, ordered legend, normalized level probabilities, and confidence; score may fall between scale levels as documented.

`DecisionResponse` contains the provider model, answers associated by question name, and usage token counts. Each answer must correspond to a submitted question and matching type. Probability values must be finite and within valid bounds; probability maps must satisfy the documented normalization rule.

## Client errors

Stable sanitized variants distinguish invalid configuration/request, transport/timeout, HTTP status, JSON decoding, and response schema failures. Public text and structured context must exclude the API key, authorization header, and untrusted raw response bodies.

## Model discovery

No `JevModel` response entity is defined until TypeSafe documents `/v1/models`. Returning inferred metadata would create an unsupported provider contract.
