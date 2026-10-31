# 快速开始：工具注册表

## 构造工具

```python
from pathlib import Path

from jev_router.tools import (
    CalculatorTool,
    KnowledgeSearchTool,
    MockEmailTool,
    SearchDocument,
    ToolRegistry,
    WebSearchMockTool,
    WriteFileTool,
)

registry = ToolRegistry([
    CalculatorTool(),
    KnowledgeSearchTool([SearchDocument(title="Guide", content="Local reference text")]),
    WebSearchMockTool(),
    WriteFileTool(Path("./workspace")),
    MockEmailTool(),
])
```

允许列表由应用构造。不要从模型输出推导注册项或权限。

## 离线执行与校验

```python
answer = registry.execute("calculator", {"expression": "(2 + 3) * 4"})
assert answer.output["result"] == 20.0
```

所有工具都提供同步的 `execute(input)` 并返回 `ToolResult`。搜索需要注入的本地数据／夹具。`write_file` 被限制在其配置的根目录内，并且除非显式配置 `allow_overwrite=True`，否则会拒绝覆盖已存在的文件。`send_mock_email` 只返回一次本地模拟。

在仓库根目录运行检查：

```sh
uv run ruff check .
uv run mypy jev_router
uv run pytest
```

不需要真实凭据或网络连接。
