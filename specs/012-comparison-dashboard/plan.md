# 实施计划：对比看板

## 设计决策

### 1. 评测结果与 trace 存放在同一个存储层

存储层已经具备版本化持久化、upsert 幂等性以及“读不懂的就拒绝”规则，因此评测运行遵循它，而不是另造一套存储机制。新增两张表：

```text
eval_runs           one row per recorded run: run_id, mode, created_at, case_count, metrics payload
eval_case_results   one row per (run_id, case_id, mode): the case outcome payload
```

`SCHEMA_VERSION` 从 1 升到 2。这次升级是增量的，而存储层本来就只拒绝*更新*的数据库，因此一个既有的第 8 阶段数据库可以原样打开并获得这两张新表。每个 JSON 列都保持 `{"version": 1, "data": ...}` 外层结构和同样的 `_encode`/`_decode` 配对，因此本次构建读不了的 payload 会显式报错，而不是静默地误读某个指标。

### 2. payload 模型由 API 拥有；命令行导入它们

`apps/api/schemas.py` 定义严格的请求/响应模型（`RecordEvalRunRequest` 等）。`evals/cli.py`——`evals/` 中唯一被允许跨越层边界的模块——导入它们来构建 `--api` 的 POST 请求体，这使得命令行不可能发出一个会被 API 拒绝的请求体。评测库本身（`cases`、`runner`、`metrics`、`llm_router`、`registry`）仍然不从 `apps/` 导入任何内容，从而保持 `docs/development.md` 中规定的依赖方向不变。

### 3. Web 层照旧做镜像

`src/lib/types.ts` 手工镜像新的传输模型，`src/lib/api.ts` 新增 `listEvalRuns`/`getEvalRun`，沿用同样的可注入 fetch 与错误映射，`src/lib/viewModel.ts` 新增把一次运行转换成卡片与表格行的纯函数。组件只负责布局。缺失的指标渲染为“—”，与既有规则一致：`NULL` 与真实的 `0` 是不同的事实。

### 4. 两个页面，不引入新的导航机制

`/evals` 列出各次运行，并展示每次运行指标的聚合卡片；`/evals/[runId]` 渲染逐用例对比表。头部新增一个链接。刻意不做轮询：一次评测运行是一份已完成的记录，而不是一个进行中的进程。

## 文件布局

```text
apps/api/storage.py      + eval_runs / eval_case_results, record/list/load, SCHEMA_VERSION 2
apps/api/schemas.py      + RecordEvalRunRequest, payload models, read views
apps/api/app.py          + POST /evals, GET /evals, GET /evals/{run_id}
evals/cli.py             + --api URL (posts the finished report)
apps/web/src/lib/types.ts     + eval mirrors
apps/web/src/lib/api.ts       + listEvalRuns, getEvalRun
apps/web/src/lib/viewModel.ts + eval card/row view model
apps/web/src/app/evals/page.tsx
apps/web/src/app/evals/[runId]/page.tsx
tests/test_storage.py    + eval run round-trip, idempotence, versioned payload refusal
tests/test_api.py        + endpoint schema, 404/422 mapping, round-trip through the service
apps/web/src/lib/viewModel.test.ts, api.test.ts + eval coverage
```

## 测试策略

- 存储：使用临时 SQLite 文件，对一次已记录运行做往返读写、重复记录同一个 id、拒绝被篡改的 payload 外层结构。
- API：使用注入存储层的 `TestClient`；断言状态码，以及对外提供的视图与提交内容一致。
- Web：用 vitest 配合桩化 fetch，覆盖新的视图模型函数与客户端方法，然后运行 `tsc --noEmit`、lint 与 `next build`。

## 风险

- **schema 版本升级**：旧数据库必须继续可用。通过采用增量改动来缓解，并在测试中打开一个 version-1 数据库来覆盖。
- **报告体积**：50 个用例 × 两种模式，每次运行有几百行；列表由 `limit` 限定范围，详情页只加载一次运行。
