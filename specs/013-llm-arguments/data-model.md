# 数据模型：LLM 参数合成

## `Tool.input_model` (`jev_router/tools/base.py`)

```python
class Tool(Protocol):
    name: str
    description: str
    risk: RiskLevel
    input_model: type[BaseModel]

    def execute(self, input: dict[str, Any]) -> ToolResult: ...
```

工具 `execute` 本就据以校验的 pydantic 模型。它是两个使用方的单一事实来源：工具
自身的校验，以及参数解析器构建的提示词。除此之外没有任何东西描述工具的输入，因此
二者不会漂移——危险的方向正在于此，因为漂移的提示词会宣称某个工具会拒绝的字段，
从而看起来像一次成功的调用。

在每个工具上声明的类型被放宽为 `type[BaseModel]`
（`input_model: type[BaseModel] = CalculatorInput`），因为协议成员是不变的：
`type[CalculatorInput]` 不能赋值给 `type[BaseModel]`。

| 工具 | 模型 | 说明 |
| --- | --- | --- |
| `calculator` | `CalculatorInput` | `expression`，最大 256 |
| `knowledge_search` | `SearchInput` | `query`，可选 `limit` |
| `web_search` | `SearchInput` | 与知识搜索共用 |
| `write_file` | `WriteFileInput` | `path`、`content` |
| `send_mock_email` | `MockEmailInput` | `to`、`subject`、`body` |

现在每个字段都带有 `Field(description=...)`。此前生成的 schema 只写
`{"expression": {"type": "string", "maxLength": 256}}`——足以猜出字段名，但不足
以产出一个*正确*的值。`write_file` 的路径规则（相对路径、位于工作区根目录内、
不覆盖已存在文件）存在于工具的实现体内，因此没有散文说明时模型会输出绝对路径，
每次写入都会失败。

## 解析器 (`apps/api/llm.py`)

```text
LLMArgumentResolver(client: Completer, model: str, tools: ToolRegistry)
    async def resolve(action: str, state: TaskState) -> dict[str, Any]
```

提示词各段落依次为：状态块（目标、步骤、上下文、裁剪后的历史、上一次结果）、
动作、工具的描述与风险等级、渲染出的 schema，以及响应契约。

schema 渲染器为每个字段输出一行：

```text
- path (string, required) [min length 1; max length 512]: A relative path inside the workspace root; absolute paths and '..' are refused, and an existing file is not overwritten.
- limit (integer, optional, defaults to 5) [min 1; max 20]: How many results to return at most.
```

只渲染会影响工具是否接受该值的内容——标题与 `additionalProperties` 被丢弃。

解析：先把整个补全结果当作 JSON 尝试，再提取第一个括号配平的对象（因此围栏包裹的
答案也可用）。结果必须是一个非空对象，且至少与工具字段有一个共同的键。其余情况都
抛出 `ValueError`，它会从 `Runner.run()` 逃逸，并经 `TaskService._drive` 既有的
兜底捕获变成一次失败的运行。

解析器原样返回模型给出的对象。未知键*不*会被过滤：每个输入模型上的
`extra="forbid"` 意味着工具会拒绝它们，而在此处过滤会让解析器成为第二个、更弱的
权威。

## 装配 (`apps/api/service.py`)

```python
self._delegate, llm_resolver = self._build_llm_collaborators(llm_client)
self._resolver = resolver if resolver is not None else llm_resolver
```

一组配置项（`llm`、`llm_model`）同时驱动这两个协作者。显式注入的 `resolver` 优先
于 LLM 提供的那个，因为注入是调用方自己的接缝——测试套件依赖这一点。

## 无新增持久化状态

本阶段的任何内容都不会进入数据库。解析器产出的参数已经落在 `StepTrace.arguments`
中，因而也落在 `agent_steps` 中，因为执行循环（Runner）记录它们的方式与记录注入式
解析器的参数完全相同。
