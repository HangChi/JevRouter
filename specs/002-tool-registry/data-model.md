# Data Model: Tool Registry

## RiskLevel

A literal classification assigned by the tool implementation/configuration: `read`, `write`, or `external`. It is descriptive metadata and is not an authorization decision.

## Tool

A synchronous protocol with:

- `name`: stable registry key.
- `description`: short purpose statement.
- `risk`: `RiskLevel` metadata.
- `execute(input: dict[str, Any]) -> ToolResult`: validates and executes a single invocation.

## ToolResult

- `tool_name`: name of the producing tool.
- `output`: structured JSON-like output object.

## ToolRegistry

An in-memory mapping of unique tool names to preconstructed trusted `Tool` instances. Supports registration, lookup, ordered name listing, and dispatch. Missing names and duplicate names are errors. Registry membership does not imply that an invocation is authorized.

## MVP Inputs and Outputs

- `CalculatorInput`: bounded arithmetic expression. Output contains a numeric `result`.
- `SearchInput`: bounded query and result `limit` (1–20). `SearchDocument`: bounded title/content and optional URL. Search results are limited and content excerpts are capped at 1000 characters.
- `WriteFileInput`: relative `path` and bounded text `content`. Output reports relative path and UTF-8 byte count.
- `MockEmailInput`: bounded recipient, subject, and body. Output reports `simulated`, recipient, and subject; body is not echoed.

Search records/fixtures are injected in memory. File root, overwrite policy, and byte ceiling are constructor configuration.
