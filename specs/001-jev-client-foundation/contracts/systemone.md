# POST /v1/systemone

## 状态

已于 2026-09-23 对照 TypeSafe HTTP API 参考进行验证。本契约只覆盖文档所述的请求字段与类型化决策响应字段。未文档化的字段不做推断。

## 请求

- 方法／路径：`POST /v1/systemone`
- 鉴权：`Authorization: Bearer <API_KEY>`
- 内容类型：`application/json`
- JSON 对象：
  - `state`：字符串、对象或数组。
  - `model`：调用方选择的字符串标识符。
  - `questions`：以问题名称为键的非空对象。
- 每个问题都有 `type` 和 `instructions`；instructions 可以是字符串、对象或数组。
- `noul`：可选，描述真／假的条件（criteria）。
- `choice`：criteria 是一个映射，至多 255 个候选标识符对应到各自描述。
- `score`：criteria 是由 2–10 个量程标签组成的有序数组。

## 响应

- JSON 对象包含 `model`、`answers`，以及带输入／输出 token 计数的 `usage`。
- `answers` 以所提交的问题名称为键。
- Noul 答案：`type` 以及落在 `[0, 1]` 内的 `noul` 概率。
- Choice 答案：`type`、`choice`、`probabilities` 和 `confidence`；概率分布遵循提供方文档所述的归一化规则。
- Score 答案：`type`、数值 `score`、`legend`、`probabilities` 和 `confidence`；分数可以位于图例层级之间，概率遵循文档所述的归一化规则。
- 答案类型必须与所提交的问题类型一致。

## 错误与客户端处理

TypeSafe 文档所述的状态码包括鉴权／校验、限流和服务容量类，如 401、422、429 和 529。适配器对外暴露脱敏的类型化 HTTP 失败，并且不自动重试。它不会暴露鉴权数据或原始响应内容。

## 特性范围

本特性只覆盖 `POST /v1/systemone`；模型发现不在其范围之内。
