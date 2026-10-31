# 任务：LLM 参数合成

## 阶段 1：工具协议与输入模型

- [x] T001 在 `jev_router/tools/base.py` 的 `Tool` 协议中添加 `input_model: type[BaseModel]`，并在全部五个工具上声明它，复用每个 `execute` 本就据以校验的 pydantic 模型（两个搜索工具共用 `SearchInput`）。
- [x] T002 为四个输入模型（`CalculatorInput`、`WriteFileInput`、`MockEmailInput`、`SearchInput`）添加 `Field(description=...)`，使生成的 schema 携带模型所需的散文式约束说明；校验行为保持不变。
- [x] T003 更新 `tests/` 中三个桩工具，使其声明输入模型，并添加一个测试，断言每个已注册工具都声明了一个其 `execute` 接受的模型。

## 阶段 2：解析器

- [x] T004 实现 `apps/api/llm.py`：把委托处理器从 `service.py` 移出，并添加 `LLMArgumentResolver`，包含提示词构建器、schema 渲染器（类型、必填/可选、有效性约束、描述）以及会抛出携带失败原因的 `ValueError` 的严格 JSON 解析。
- [x] T005 对 `apps/api/llm.py` 做单元测试：提示词携带目标、步骤、历史、动作、描述、风险等级以及每个字段行；裸 JSON 与围栏 JSON 都能解析；非对象、缺失键和非字符串值各自抛出异常；provider 错误携带其类别；历史会被裁剪。
- [x] T006 把解析器接入 `TaskService`，与委托相邻；二者都由同一组 `llm`/`llm_model` 装配，且在未配置时都不存在。

## 阶段 3：端到端与检查

- [x] T007 测试一次穿过 HTTP 边界的完整运行：路由到 `calculator` 后用模型合成出的参数执行，trace 记录这些参数，工具的真实输出落入结果。
- [x] T008 端到端测试失败路径：provider 错误与格式错误的补全各自产生一次失败运行，其诊断信息指明原因；未配置的服务仍按第 7 阶段交付的方式失败。
- [x] T009 更新 `README.md`、`docs/development.md`、`docs/architecture.md` 与 `docs/security.md`，以覆盖解析器、协议变更以及围绕模型产出参数的信任边界。
- [x] T010 编写本规格目录下的 `data-model.md` 与 `quickstart.md`，运行 ruff、对 `jev_router apps evals` 的严格 mypy 以及完整的 pytest 套件，然后对真实应用进行验证：用桩实现的 Jev 与 LLM 客户端在 uvicorn 下启动 `apps.api`，并通过 curl 驱动一次执行真实工具的运行。

## 依赖关系

T001 先于 T002/T003。T001–T003 先于 T004。T004 先于 T005/T006。T006 先于 T007/T008。T009–T010 在实施之后进行。

## 完成标准

所有任务只有在实施与验证之后才会被勾选。不改动 `Runner`、任何工具的校验行为或策略引擎的阈值，且 `jev_router/` 仍然不从 `apps/` 导入任何内容。
