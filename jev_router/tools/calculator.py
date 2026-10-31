from __future__ import annotations

import ast
import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from jev_router.tools.base import RiskLevel, ToolResult


class CalculatorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str = Field(
        min_length=1,
        max_length=256,
        description=(
            "One arithmetic expression using + - * / // % ** and parentheses, "
            "with numeric literals only."
        ),
    )


_BINARY_OPERATORS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
_UNARY_OPERATORS = (ast.UAdd, ast.USub)


def _apply_binary(operation: ast.operator, left: float, right: float) -> float:
    if isinstance(operation, ast.Add):
        result = left + right
    elif isinstance(operation, ast.Sub):
        result = left - right
    elif isinstance(operation, ast.Mult):
        result = left * right
    elif isinstance(operation, ast.Div):
        result = left / right
    elif isinstance(operation, ast.FloorDiv):
        result = left // right
    elif isinstance(operation, ast.Mod):
        result = left % right
    elif isinstance(operation, ast.Pow):
        result = left**right
    else:
        raise TypeError("不支持的算术运算符")
    return float(result)


def _apply_unary(operation: ast.unaryop, value: float) -> float:
    if isinstance(operation, ast.UAdd):
        return value
    if isinstance(operation, ast.USub):
        return -value
    raise ValueError("不支持的算术运算符")


class CalculatorTool:
    name = "calculator"
    description = "Evaluate a bounded arithmetic expression."
    risk: RiskLevel = "read"
    input_model: type[BaseModel] = CalculatorInput

    def execute(self, input: dict[str, Any]) -> ToolResult:
        try:
            request = CalculatorInput.model_validate(input)
            tree = ast.parse(request.expression, mode="eval")
            result = _evaluate(tree.body, 0)
        except (ValidationError, SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
            raise ValueError("无效或不支持的算术表达式") from exc
        if not math.isfinite(result):
            raise ValueError("算术结果必须是有限值")
        return ToolResult(tool_name=self.name, output={"result": result})


def _evaluate(node: ast.AST, depth: int) -> float:
    if depth > 20:
        raise ValueError("表达式嵌套过深")
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        value = float(node.value)
        if not math.isfinite(value):
            raise ValueError("数值字面量必须是有限值")
        return value
    if isinstance(node, ast.BinOp) and isinstance(node.op, _BINARY_OPERATORS):
        left = _evaluate(node.left, depth + 1)
        right = _evaluate(node.right, depth + 1)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("指数超出范围")
        return float(_apply_binary(node.op, left, right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, _UNARY_OPERATORS):
        return float(_apply_unary(node.op, _evaluate(node.operand, depth + 1)))
    raise ValueError("不支持的算术表达式")
