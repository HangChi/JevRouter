# 任务：有界执行循环（Runner）

## 阶段 1：执行循环契约

- [x] T001 将 `jsonable()` 提取到 `jev_router/serialization.py`，并在 `verifier.py` 中复用。
- [x] T002 在 `jev_router/runner.py` 中定义 `RunStatus`、`StepTrace`、`RunResult` 以及协作者协议。
- [x] T003 在构造时校验模型标识符、完成度阈值以及 `max_model_calls >= 2 * max_steps` 预算不变式。
- [x] T004 由共享的单个 `ToolRegistry` 组装 `Router`、`PolicyEngine` 与 `Verifier`。

## 阶段 2：循环

- [x] T005 在消耗任一计数器之前先检查两个预算计数器，然后每次迭代消耗一步与一次路由模型调用。
- [x] T006 映射策略结果：`reject`、`ask_user`、`delegate_to_llm`、`execute`/`ask_confirmation` 以及 `finish`。
- [x] T007 在确认之前解析参数，并将其绑定到 `ConfirmationHandler` 调用。
- [x] T008 对 `write` 与 `external` 风险工具要求确认，独立于策略结果。
- [x] T009 当必需的协作者缺失时按失败关闭。
- [x] T010 在执行之后执行验证，并在至少有一步骤时对 `finish` 推荐执行验证；若尚未运行任何步骤则跳过验证。
- [x] T011 对未变化状态的第二次否定评估以 `failed` 停止。
- [x] T012 把提供商、工具、解析器与状态错误转换为带诊断信息的 `failed`。
- [x] T013 每次迭代输出一个 trace，决策前终止时也输出一个，且不让 sink 失败中止运行。

## 阶段 3：测试与文档

- [x] T014 从包中导出公开的执行循环类型。
- [x] T015 在 `tests/test_runner.py` 中测试完成、继续、结束、预算耗尽、确认门控、委托、用户输入、失败模式、trace 与不可变性。
- [x] T016 在本规格目录中记录范围、数据模型与阶段边界。
- [x] T017 更新架构与开发文档，说明执行循环（Runner）的预算归属与失败关闭的默认行为。
- [x] T018 运行 Ruff、严格模式 mypy 与完整的离线 pytest；审查权责边界。

## 依赖

T001 先于 T002 与 T012。T002–T004 先于 T005–T013。T014–T018 在实现与测试之后进行。

## 完成标准

所有任务仅在实现与验证完成之后才会被勾选。执行循环（Runner）负责预算消耗与终止；它不原地修改状态、不执行未注册的动作、不在人类身上阻塞等待，也不实现 LLM 适配器。
