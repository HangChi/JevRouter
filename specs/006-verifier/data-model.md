# 数据模型：Jev 验证器

## VerificationDecision

由一次 Jev 请求返回的不可变评估：

- `completion_probability`：Noul 对当前结果满足目标的估计。
- `quality_score`：数值型的结果质量分。
- `quality_confidence`：为该分数报告的置信度。
- `quality_legend`：用于质量分问题的有序标签。
- `model`：提供商返回的模型标识符。

`NoulAnswer` 只携带一个概率，因此完成度评估没有单独的置信度值；`quality_confidence` 来自质量分答案。

## Verifier

一个异步适配器，使用 `JevClient` 与显式的模型标识符进行配置。它接受已完成的 `TaskState`，一并请求完成度与质量，并返回 `VerificationDecision`，而不修改状态，也不决定后续发生什么。
