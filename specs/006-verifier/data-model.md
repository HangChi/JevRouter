# Data Model: Jev Verifier

## VerificationDecision

An immutable assessment returned by one Jev request:

- `completion_probability`: Noul estimate that the current result satisfies the goal.
- `quality_score`: numeric result quality score.
- `quality_confidence`: confidence reported for that score.
- `quality_legend`: ordered labels used in the score question.
- `model`: model identifier returned by the provider.

`NoulAnswer` carries only a probability, so the completion assessment has no separate confidence value; `quality_confidence` comes from the score answer.

## Verifier

An asynchronous adapter configured with a `JevClient` and explicit model identifier. It accepts a completed `TaskState`, requests completion and quality together, and returns `VerificationDecision` without modifying the state or deciding what happens next.
