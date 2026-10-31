# 数据模型：对比看板

## 表 (`apps/api/storage.py`)

```text
eval_runs (
    run_id     TEXT PRIMARY KEY,
    mode       TEXT NOT NULL,      -- jev | llm | compare
    created_at TEXT NOT NULL,      -- UTC ISO-8601 from the eval report
    metrics    TEXT NOT NULL       -- {"version": 1, "data": ComparisonMetricsPayload}
)

eval_case_results (
    run_id  TEXT NOT NULL,
    case_id TEXT NOT NULL,
    mode    TEXT NOT NULL,         -- jev | llm
    payload TEXT NOT NULL,         -- {"version": 1, "data": EvalCaseOutcomePayload}
    PRIMARY KEY (run_id, case_id, mode),
    FOREIGN KEY (run_id) REFERENCES eval_runs (run_id) ON DELETE CASCADE
)
```

`SCHEMA_VERSION` 从 1 升到 2。该改动是增量的，而存储层只拒绝比本次构建*更新*的数据库，因此既有的第 8 阶段数据库可以原样打开并获得这些表；有一个测试专门覆盖这一点。

两个 payload 列都使用存储层已有的 `_encode`/`_decode` 配对。`_encode` 会降级处理 JSON 无法承载的值，但 pydantic 模型不属于可承载之列——`jsonable` 会拒绝 `BaseModel` 并把它静默降级为 `{"__unserializable__": ...}`——因此先用 `model_dump(mode="json")` 把模型转储为普通 dict。

## 传输模型 (`apps/api/schemas.py`)

`RecordEvalRunRequest` 是 POST 请求体：`run_id`、`mode`、`created_at`、`outcomes`、`metrics`。它不携带 `case_count`：该值由去重后的 case id 推导而来，因此一份报告无法声称一个与自身行相矛盾的计数。

字段范围之外的校验：

- `mode` 必须是 `jev`、`llm`、`compare` 之一。
- 每个结果的 `mode` 必须属于该次运行的模式（`jev` → 仅 jev 行，`compare` → 两者皆有）。
- 一次 compare 运行必须在两个路由层上配对每个用例：jev 的 case-id 集合必须等于 llm 的集合。
- 比率约束在 `[0, 1]` 区间，计数与延迟约束为非负。

`ComparisonMetricsPayload` 持有 `jev`、`llm`、`agreement_count`、`compared_count`、`agreement_rate`、`disagreement_case_ids`。`ModeMetricsPayload` 中的策略字段在基线模式下为 `None`。除非两种模式各自至少回答了一个用例，否则 `agreement_rate` 为 `None`，并且 API 不会重新计算它：各比率随数据一同传输，因此已存储的报告在不依赖本次构建的算术逻辑时仍可解读。

## 读取视图

`EvalRunSummary`（列表行：运行 id、模式、created_at、用例数）与 `EvalRunView`（摘要 + 指标 + 结果）。`case_count` 是去重后的 case id 数量，因此一次 50 个用例的 compare 运行报告 50，而不是 100 行。

`load_eval_run` 按 `(case_id, mode)` 排序行，这样同一个用例的两个路由层行会相邻，同一用例集的两次运行也会逐行对齐。

## 命令行桥接

`--api URL` 会把 `report_to_dict(report)["data"]`——即外层结构中的 payload，而非外层结构本身——POST 到 `POST /evals`。被拒绝时会带上 API 自己的消息并退出 `3`（`EXIT_DELIVERY`），与用例错误（`1`）和配置问题（`2`）区分开。
