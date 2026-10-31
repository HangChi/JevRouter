from __future__ import annotations

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

# 固定 fixture，保证运行可复现：评测衡量的是路由，候选描述来自注册表，
# 而不是其背后的数据。
KNOWLEDGE_FIXTURES: tuple[SearchDocument, ...] = (
    SearchDocument(
        title="差旅政策",
        content="每日餐补为 500 元；酒店每晚最多报销 600 元。",
    ),
    SearchDocument(
        title="API 速率限制",
        content="公共 API 允许每个密钥每分钟 600 次请求，突发上限为 60 次。",
    ),
    SearchDocument(
        title="入职清单",
        content="新员工需完成账号开通、安全培训、团队介绍和第一个项目。",
    ),
    SearchDocument(
        title="企业版定价",
        content="企业版为每席位每年 2400 元，最少二十个席位。",
    ),
    SearchDocument(
        title="退款政策",
        content="购买后 14 天内，未使用的席位可以退款。",
    ),
    SearchDocument(
        title="备份计划",
        content="数据库每六小时备份一次，保留 30 天。",
    ),
    SearchDocument(
        title="服务级别协议",
        content="对于付费套餐，我们承诺每月 99.9% 的可用性。",
    ),
    SearchDocument(
        title="休假政策",
        content="全职员工每年累积 15 天带薪年假。",
    ),
)

WEB_FIXTURES: tuple[SearchDocument, ...] = (
    SearchDocument(
        title="东京明日天气",
        content="东京明天：有雨，最高 24C、最低 19C，阵雨概率 70%。",
        url="https://example.invalid/tokyo-weather",
    ),
    SearchDocument(
        title="Python 发布说明",
        content="最新的 Python 稳定版带来了性能改进和新的类型特性。",
        url="https://example.invalid/python-release",
    ),
    SearchDocument(
        title="汇率",
        content="最新更新中，美元兑人民币报价为 7.18。",
        url="https://example.invalid/fx",
    ),
)


def default_registry(workspace_root: str | Path) -> ToolRegistry:
    """五个 MVP 工具，搭配固定 fixture，根目录由调用方提供。"""
    root = Path(workspace_root)
    root.mkdir(parents=True, exist_ok=True)
    return ToolRegistry(
        [
            CalculatorTool(),
            KnowledgeSearchTool(KNOWLEDGE_FIXTURES),
            WebSearchMockTool(WEB_FIXTURES),
            WriteFileTool(root),
            MockEmailTool(),
        ]
    )
