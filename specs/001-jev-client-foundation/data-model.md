# 数据模型：Jev 客户端基础

## JevClientConfig

- `base_url`：绝对的服务 URL，默认取文档所述的 TypeSafe API 源站；在明确受控的测试之外必须是 HTTPS。
- `api_key`：由环境／配置提供的必需机密；不参与表示和错误信息。
- `timeout_seconds`：有限的、正数的请求总超时。

## QuestionDefinition

一个问题名称映射到某一种受支持的变体：

- `NoulQuestion`：`type="noul"`，必需指令（字符串／对象／数组），可选描述真／假的条件（criteria）。
- `ChoiceQuestion`：`type="choice"`，必需指令，以及将候选标识符映射到描述的 criteria；criteria 包含 1–255 个候选。
- `ScoreQuestion`：`type="score"`，必需指令，以及带 2–10 个量程标签的有序 criteria。

问题名称在 `DecisionRequest.questions` 中映射到问题定义；请求校验会在网络 I/O 之前拒绝空的问题集合和不支持的定义。

## DecisionRequest

- `model`：调用方提供的提供方模型标识符；不硬编码为某个账户专属取值。
- `state`：与 JSON 兼容的字符串、对象或数组。
- `questions`：从问题名称到类型化问题定义的非空映射。

## 答案变体

- `NoulAnswer`：类型判别符，以及落在 `[0, 1]` 内的 `noul` 概率；不假设存在独立的置信度字段。
- `ChoiceAnswer`：类型判别符、所选项、归一化的候选概率，以及置信度；所选选项必须在所提交的候选之中。
- `ScoreAnswer`：类型判别符、数值分数、有序图例、归一化的层级概率，以及置信度；分数可以如文档所述落在量程层级之间。

`DecisionResponse` 包含提供方模型、按问题名称关联的答案，以及 usage 的 token 计数。每个答案都必须对应一个已提交的问题且类型匹配。概率取值必须是有限的并处于合法边界内；概率映射必须满足文档所述的归一化规则。

## 客户端错误

稳定的脱敏变体用于区分非法配置／请求、传输／超时、HTTP 状态、JSON 解码和响应 schema 失败。对外文本和结构化上下文必须排除 API 密钥、鉴权请求头，以及不可信的原始响应体。

