# 数据模型：工具注册表

## RiskLevel

由工具实现／配置赋予的字面量分类：`read`、`write` 或 `external`。它是描述性元数据，不是授权决策。

## Tool

一个同步协议，包含：

- `name`：稳定的注册表键。
- `description`：简短用途说明。
- `risk`：`RiskLevel` 元数据。
- `execute(input: dict[str, Any]) -> ToolResult`：校验并执行一次调用。

## ToolResult

- `tool_name`：产出该结果的工具名称。
- `output`：结构化的类 JSON 输出对象。

## ToolRegistry

一个内存映射，把唯一的工具名称映射到预先构造的可信 `Tool` 实例。支持注册、查找、按顺序列出名称以及派发。名称缺失和名称重复都是错误。注册表成员资格并不意味着某次调用已获授权。

## MVP 输入与输出

- `CalculatorInput`：有边界的算术表达式。输出包含数值 `result`。
- `SearchInput`：有边界的查询和结果 `limit`（1–20）。`SearchDocument`：有边界的标题／内容和可选 URL。搜索结果数量受限，内容摘录上限为 1000 个字符。
- `WriteFileInput`：相对 `path` 和有边界的文本 `content`。输出报告相对路径和 UTF-8 字节数。
- `MockEmailInput`：有边界的收件人、主题和正文。输出报告 `simulated`、收件人和主题；正文不回显。

搜索记录／夹具在内存中注入。文件根目录、覆盖策略和字节上限属于构造函数配置。
