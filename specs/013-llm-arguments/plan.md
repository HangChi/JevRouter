# 实施计划：LLM 参数合成

## 设计决策

### 1. Tool 协议获得它本就据以校验的模型

```python
class Tool(Protocol):
    name: str
    description: str
    risk: RiskLevel
    input_model: type[BaseModel]

    def execute(self, input: dict[str, Any]) -> ToolResult: ...
```

一个无法描述自身输入的工具无法被模型驱动，而唯一诚实的描述就是校验时已经在用的
那一个。让提示词从 `input_model.model_json_schema()` 派生，就使提示词不可能宣称
某个工具会拒绝的字段——这里所避免的漂移属于危险的那一类，因为它看起来会像一次
成功的调用。

五个工具各自声明它们本就导入的模型。三个测试桩新增一行模型声明。`web_search` 与
`knowledge_search` 共用 `SearchInput`，后者已经在 `knowledge_search.py` 中。

### 2. 字段描述，而非裸类型

生成的 schema 写的是 `{"expression": {"type": "string", "maxLength": 256}}`
——足以猜出字段名，但不足以产出一个*正确*的值。`write_file` 的路径必须相对于
工作区根目录；这条规则存在于工具的实现体内，因此如果 schema 中没有散文说明，
模型就会输出绝对路径，每次写入都会失败。给四个输入模型加上
`Field(description=...)`，就把该约束放在强制执行它的代码旁边，而 schema 渲染器
会顺带取用。

### 3. 用一个模块承载基于 LLM 的协作者

`apps/api/llm.py` 同时承载 `LLMArgumentResolver` 和第 11 阶段留在 `service.py`
中的 `LLMDelegate`。它们形态相同——一个注入的客户端、一个模型、一个提示词构建器、
一套错误分类——把它们分开会导致失败处理重复。`service.py` 继续负责装配与运行
注册表。

### 4. 失败要显式，并落在执行循环（Runner）本来就放置它的地方

解析器抛出携带 provider 类别或解析问题的 `ValueError`。`Runner.run()` 让它向外
逃逸（内部只处理 `_Stop` 与 `JevClientError`），而 `TaskService._drive` 既有的
兜底捕获会把它变成一次失败的运行，并把消息放入诊断信息。这与第 11 阶段委托所用的
路径相同，而且是刻意的：一次静默产出 `{}` 的合成会以无参数执行工具，那比停止运行
更糟。

解析器原样返回模型给出的对象——不过滤、不补默认值。工具的 pydantic 模型才是权威，
因此违规的参数失败的情形与手写参数完全一致。

### 5. 提示词形态

```text
Goal: ...
Step: N
Context: {...}
Completed steps:
- step 1: web_search -> {...}
Last result: {...}

Action to perform: write_file
Description: Write a bounded text file under a configured root directory.
Risk: write

Arguments (respond with one JSON object using exactly these keys):
- path (string, required): A relative path inside the workspace root; ...
- content (string, required): The full text to write; ...

Respond with exactly one JSON object and nothing else.
```

schema 渲染器为每个字段输出一行，包含类型、必填/可选、影响有效性的约束（最小/最大
长度、最小/最大值、默认值）以及描述。标题与 `additionalProperties` 作为噪声被
丢弃。

## 文件布局

```text
jev_router/tools/base.py                 + input_model on the protocol
jev_router/tools/{calculator,write_file,mock_email,knowledge_search}.py
                                        + input_model, + field descriptions
apps/api/llm.py                          new: LLMArgumentResolver, LLMDelegate
apps/api/service.py                      assemble both, import from llm.py
tests/test_api_llm.py                    new: prompt, parse, failures, settings
tests/test_router.py, test_policy.py,
  tests/test_runner.py                   stub tools gain input_model
tests/test_api.py                        end-to-end run with a real tool
```

## 测试策略

- 解析器单元测试，使用桩化补全器：提示词携带每一个必需元素；裸 JSON 与围栏 JSON
  都能解析；非对象、缺失键和未知键各自抛出异常；provider 错误携带其类别。
- schema 渲染器测试：必填/可选、默认值、长度与范围约束，以及描述能到达该行。
- API 测试：一次路由到 `calculator` 并用合成参数执行的运行（trace 显示模型的参数
  与工具的真实输出）；合成失败产生带诊断信息的失败运行；未配置的服务行为与之前
  完全一致。
- 工具测试：五个工具的校验行为保持不变，且各自声明其 `execute` 据以校验的模型。

## 风险

- **协议变动**：新增一个必需成员会触及每个工具与测试桩。影响有界且机械；有一个
  测试断言每个已注册工具都声明了一个其字段确实被该工具接受的模型。
- **提示词体积**：历史会像委托那样被裁剪，因此一次长时间运行不会无限制地撑大
  提示词。
- **模型输出质量**：模型可能产出工具会拒绝的参数。这正是设计中的失败——运行以
  工具自己的消息停止，trace 显示曾尝试了什么。
