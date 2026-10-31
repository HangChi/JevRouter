# 参与开发

这份文档说明怎么在这个仓库里改动，以及哪些约定是硬性的。

## 环境

```sh
uv sync --all-groups          # Python + 开发依赖
cd apps/web && npm install    # 只有改前端时才需要
```

运行服务需要 Jev 凭证，但**跑测试不需要**——测试全部使用 HTTP mock 与临时数据库，不产生任何真实调用。见 [快速开始](docs/quickstart.md)。

## 提交前必须通过

```sh
uv run ruff check .
uv run mypy jev_router apps evals
uv run python scripts/check_docs.py    # 相对链接与锚点
uv run pytest
```

改动涉及前端时再加：

```sh
cd apps/web
npm run typecheck   # 含 next typegen
npm run lint
npm test
npm run build
```

CI（[`.github/workflows/ci.yml`](.github/workflows/ci.yml)）跑的就是这些，两边不一致没有意义。

> 本机若出现大量 `FileExistsError: …/pytest-of-<user>`，那是沙箱与 pytest 临时目录的冲突，与代码无关：`uv run pytest --basetemp=$PWD/.pytest_tmp`。

## 硬性约定

### 1. 核心包不依赖 Web 框架

`jev_router/` 里不应出现 FastAPI、SQLite 或任何 HTTP 路由代码。状态、路由、策略、执行循环、验证都应当能在不启动服务的情况下构造与测试。`apps/api/` 负责输入校验、配置与依赖装配，`apps/web/` 负责展示。

### 2. 模型输出是不可信输入

任何来自 Jev 或 LLM 的内容——包括概率、风险分、合成的工具参数——都只是输入。授权由代码决定，校验由工具的 pydantic 模型决定。不要因为「模型置信度高」就跳过策略层，也不要因为「参数是模型生成的」就跳过工具校验。

### 3. 失败要 fail closed

预算耗尽、依赖超时、响应格式错误、概率缺失、状态不一致——一律安全停止并留下可诊断的信息，而不是退化成一个看起来能跑通的默认值。`delegate_to_llm` 在没配 LLM 时必须明确失败，而不是假装委托成功。

### 4. 同一条规则只写一遍

「工具声明为 `write`/`external` 就必须确认」曾经同时写在执行循环和评测里，结果评测报告 17 条应确认用例触发 0 条，而线上其实确认了。规则要收敛到一处（策略引擎），其他位置跟随它的结论。

判断某个逻辑该放哪：**它是不是「能不能执行」的判断？** 是就放策略引擎；是「怎么执行」就放执行循环；是「执行得对不对」就放验证器。

### 5. 提示词改动要当成行为改动

`instructions=`、`RISK_LEVELS`、`QUALITY_LEVELS`、工具 `description`、委托的系统提示——这些是发给模型的文本。改它们会改变模型行为，让已有的评测结果失去可比性。因此：

- 提示词保持英文（文档、注释、面向人的消息用中文）。
- 改提示词要在描述里说明改了什么、为什么，并重新跑评测。
- 不要为了让某几条用例通过而往描述里塞关键词，那是对测试集过拟合。

### 6. 阈值改动要有数据

默认阈值是保守初值。要改就用 [阈值校准](docs/calibration.md) 跑一遍，并且：

- 写进 `.env` 的部署配置，不要改代码里的默认值——默认值留给还没跑过评测的人。
- 如果校准器提示 `inert_dimensions`，说明那个维度在本批用例上没有证据，不要改。
- 如果提示 `at_boundary`，先补用例，不要盲目扩大网格。

### 7. 不加 Agent 框架

不引入 LangChain / LangGraph 之类的编排框架。这个项目的核心命题就是「路由与策略怎么工作」，用了框架之后最关键的逻辑反而藏在框架里。执行循环本身只有两百行左右。

## 提交信息

沿用仓库既有风格，前缀 + 中文摘要，正文说明**为什么**：

```
fix: 把工具风险下限收敛到策略引擎，确认行为第一次可被度量

执行循环自己按工具 risk 强制确认，评测却只看 policy.outcome，同一套
规则两份实现、结论不同……（说清动机与影响）
```

前缀：`feat`、`fix`、`docs`、`test`、`chore`。摘要说结论，正文说动机；不要用「修改了若干文件」这类信息量为零的描述。

一次提交只做一件事。修复和新功能混在一起时，review 的人无法判断哪部分引入了风险。

## 改动的常见落点

| 想做的事 | 先看 |
| --- | --- |
| 加一个工具 | `jev_router/tools/` 下照现有实现写，声明 `risk` 与 `input_model`，注册到 `apps/api/app.py` 的 `default_registry` |
| 改策略判定 | `jev_router/policy.py`，同时更新 `tests/test_policy.py` 与文档里的判定顺序 |
| 加 HTTP 端点 | `apps/api/app.py` 与 `schemas.py`；注意所有端点都要挂 `require_token` |
| 改评测指标 | `evals/metrics.py` 与 `apps/api/schemas.py` 的对应 payload，两边字段必须同步 |
| 改前端展示 | `apps/web/src/lib/viewModel.ts` 放纯逻辑，组件只负责布局；纯逻辑要能被 vitest 直接测 |

## 文档

改行为就顺手改文档，否则下一轮排查会照着过期文档走：

- 配置项 → [`docs/configuration.md`](docs/configuration.md) 与 `.env.example`
- 端点 / 字段 → [`docs/api.md`](docs/api.md)
- 设计理由 → [`docs/architecture.md`](docs/architecture.md)
- 安全边界 → [`docs/security.md`](docs/security.md)
- 实测数据 → [`docs/calibration.md`](docs/calibration.md)

`.env.example` 只放占位符。真实凭证永不入库——提交前用 `git diff --cached` 复查一遍。

## 提交 PR

1. 从 `main` 开分支，名字体现意图（`fix/confirmation-digest`）。
2. 确保上面的检查清单全绿。
3. PR 描述写清楚：改了什么、为什么、怎么验证的。涉及提示词或阈值时，附上前后对比数据。
4. 不要在一个 PR 里同时做重构和行为变更。
