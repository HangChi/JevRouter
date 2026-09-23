# Data Model: Decision Router

## RouterAction

A choice candidate is either a registered tool name or one of `ask_user`, `delegate_to_llm`, and `finish`. The candidate set is built from trusted registry configuration, not model output.

## RiskDescription

The ordered score legend contains: no meaningful side effects; minor reversible side effects; meaningful but reversible action; external or consequential action; potential destructive or irreversible action. Jev returns a numeric score and the exact legend used in the request.

## RouteDecision

An immutable internal result containing:

- `action`: selected tool name or control action.
- `confidence`: Jev confidence for the selected action.
- `risk`: numeric risk score and `risk_confidence`.
- `requires_confirmation`: Noul probability.
- `needs_reasoning`: Noul probability.
- `model`: model identifier returned by Jev.

These values are recommendations and measurements, not authorization or permission to execute.

## Router

An async adapter over `JevClient.systemone`, configured with a model identifier and a trusted `ToolRegistry`. A route request consumes caller-supplied JSON-compatible state and makes exactly one client call. It has no tool execution responsibility.
