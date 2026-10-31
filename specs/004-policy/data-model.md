# 数据模型：策略引擎

## PolicyOutcome

一个有限的控制结果：`execute`、`ask_confirmation`、`delegate_to_llm`、`ask_user`、`finish` 或 `reject`。

## PolicyDecision

一个不可变的结果，包含：

- `outcome`：由本地策略选出的下一个控制结果。
- `action`：路由层（Router）的原始建议。
- `reason`：对所匹配控制规则的简明解释。

## PolicyEngine

一个同步求值器，配置可信的 `ToolRegistry`。它映射固定的控制动作，对工具动作检查当前注册情况，然后应用显式的置信度、风险、确认与推理阈值。它不调用工具，也不存储或校验用户批准。
