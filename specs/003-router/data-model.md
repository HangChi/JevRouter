# 数据模型：决策路由层

## RouterAction

一个 choice 候选要么是某个已注册工具的名称，要么是 `ask_user`、`delegate_to_llm` 和 `finish` 之一。候选集合由可信的注册表配置构建，而不是由模型输出构建。

## RiskDescription

有序的评分图例包含：无实质副作用；轻微且可逆的副作用；有意义但可逆的动作；外部性或后果重大的动作；可能造成破坏或不可逆的动作。Jev 返回数值分数以及在请求中所使用的确切图例。

## RouteDecision

一个不可变的内部结果，包含：

- `action`：所选工具名称或控制动作。
- `confidence`：Jev 针对所选动作给出的置信度。
- `risk`：数值风险分数和 `risk_confidence`。
- `requires_confirmation`：Noul 概率。
- `needs_reasoning`：Noul 概率。
- `model`：Jev 返回的模型标识符。

这些取值是建议和度量，而非授权或许可执行的凭据。

## Router

一个基于 `JevClient.systemone` 的异步适配器，配置一个模型标识符和一个可信的 `ToolRegistry`。一次路由请求消费调用方提供的、与 JSON 兼容的状态，并且只发起一次客户端调用。它不承担任何工具执行职责。
