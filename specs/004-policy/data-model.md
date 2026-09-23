# Data Model: Policy Engine

## PolicyOutcome

A finite control outcome: `execute`, `ask_confirmation`, `delegate_to_llm`, `ask_user`, `finish`, or `reject`.

## PolicyDecision

An immutable result containing:

- `outcome`: the next control outcome selected by local policy.
- `action`: the original Router recommendation.
- `reason`: concise explanation of the matched control rule.

## PolicyEngine

A synchronous evaluator configured with the trusted `ToolRegistry`. It maps fixed control actions, checks current registration for tool actions, then applies explicit confidence, risk, confirmation, and reasoning thresholds. It does not call a tool or store/verify user approval.
