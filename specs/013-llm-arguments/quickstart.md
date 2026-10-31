# 快速开始：LLM 参数合成

## 运行检查

```sh
uv run ruff check .
uv run mypy jev_router apps evals
uv run pytest
```

## 配置

解析器与委托共用一份配置：

```sh
export JEV_API_KEY=... JEV_MODEL=...
export LLM_API_KEY=... LLM_MODEL=...     # optional; both or neither
```

在没有这一对 LLM 变量时，一切不变：解析器不存在，工具调用解析为 `{}`，工具自身的
schema 会拒绝它，运行以 `tool 'X' rejected its input` 停止。

`LLM_MAX_TOKENS`（默认 1024）限制了模型能生成的内容量，因此也限制了合成出的文件
内容。一次需要写入超大内容的运行需要更高的取值——工具自身的上限是 1,000,000 字节。

## 观察它工作

提交一个需要工具的目标：

```sh
uv run uvicorn apps.api.app:create_app --factory
curl -s localhost:8000/tasks -H 'content-type: application/json' \
  -d '{"goal": "Calculate 6 * 7"}'
curl -s localhost:8000/tasks/<task_id>/traces | python3 -m json.tool
```

trace 中的该步骤会显示模型原样产出的 `arguments`、工具的真实输出在 `result` 中，
以及 `executed: true`。

## 添加一个工具

声明 `execute` 据以校验的模型，并描述各字段：

```python
class MyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str = Field(min_length=1, description="What to act on.")


class MyTool:
    name = "my_tool"
    description = "Does the thing."
    risk: RiskLevel = "read"
    input_model: type[BaseModel] = MyInput

    def execute(self, input: dict[str, Any]) -> ToolResult:
        request = MyInput.model_validate(input)
        ...
```

描述是模型读到的东西，因此要写明代码所强制的约束（相对路径、白名单、大小上限），
而不是复述类型。有一个测试断言每个已注册工具都声明了一个其 `execute` 接受的模型。

## 对真实应用进行验证

用桩实现替换 provider 后启动（在 `/tmp` 下写一个临时脚本）：把 Jev 客户端桩成一次
路由到 `calculator`、一次验证通过，把 LLM 客户端桩成返回 `{"expression": "6 * 7"}`，
并把 `llm_client=<stub>` 传给 `create_app`，同时保持 `resolver` 未设置。然后：

```sh
curl -s localhost:8000/tasks -H 'content-type: application/json' \
  -d '{"goal": "Calculate 6 * 7"}'
curl -s localhost:8000/tasks/<task_id>/traces
```

预期得到 `completed`、`arguments == {"expression": "6 * 7"}` 以及
`result == {"result": 42.0}`。

## 失败路径

| 情形 | 结果 |
| --- | --- |
| 合成过程中 provider 出错 | 运行失败，诊断信息 `argument synthesis failed: <category>` |
| 补全结果不是 JSON 对象、为空，或未给出任何被接受的字段 | 运行失败，诊断信息指明解析问题 |
| 模型返回的参数字被工具拒绝 | 运行失败，附工具自己的消息；尝试过的参数仍保留在 trace 中 |
| 未配置 LLM | 与第 7 阶段行为一致 |
