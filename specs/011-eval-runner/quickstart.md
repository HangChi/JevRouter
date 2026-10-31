# 快速开始：评测执行循环（Runner）与 LLM 基线

## 运行检查

```sh
uv run ruff check .
uv run mypy jev_router apps evals
uv run pytest
```

## 对真实 provider 运行一次评测

凭据来自环境变量（命令行不会加载 `.env`）：

```sh
export JEV_API_KEY=...      # required for jev and compare
export JEV_MODEL=...        # required for jev and compare
export LLM_API_KEY=...      # required for llm and compare
export LLM_MODEL=...        # required for llm and compare

uv run python -m evals --mode compare --json-out /tmp/report.json
```

退出码：`0` 表示干净，`1` 表示至少有一个用例出错，`2` 表示配置或用例文件有问题。凭据缺失时会在任何用例运行之前失败。

其他参数：`--cases PATH`（另一个版本化用例文件）、`--limit N`（按文件顺序取前 N 个用例）、`--jev-model` / `--llm-model`（覆盖环境变量）。

报告格式为 `{"version": 1, "data": {...}}`；`data` 就是第 12 阶段 `POST /evals` 所接受的内容。

## 离线运行评测（无需凭据）

库接收的是路由层，因此一次运行不需要任何 provider：

```python
import asyncio
from evals.cases import load_cases
from evals.registry import default_registry
from evals.runner import EvalRunner
from jev_router.clients.jev import JevClient, JevClientConfig
from jev_router.router import Router

cases = load_cases()[:3]
report = asyncio.run(
    EvalRunner(
        cases=cases,
        tools=default_registry("/tmp/jevrouter-eval"),
        jev_router=Router(JevClient(JevClientConfig(api_key="x")), "model", default_registry("/tmp/jevrouter-eval")),
    ).run("jev")
)
print(report.metrics.jev.expected_match_rate)
```

`tests/test_eval_runner.py` 正是用 `httpx.MockTransport` 驱动这一形态。

## 试用 LLM 适配器

```python
import asyncio
from jev_router.clients.llm import LLMClient, LLMClientConfig

client = LLMClient(LLMClientConfig.from_env())
completion = asyncio.run(
    client.complete(model="claude-sonnet-4-5", system="Be terse.", prompt="2 + 2?")
)
print(completion.text, completion.input_tokens, completion.output_tokens)
```

## 在 API 中启用委托

```sh
export JEV_API_KEY=... JEV_MODEL=...
export LLM_API_KEY=... LLM_MODEL=...     # optional; both or neither
uv run uvicorn apps.api.app:create_app --factory
```

在配置了这一对 LLM 变量后，被策略引擎送往 `delegate_to_llm` 的路由会由该模型回答，并记录为该步骤的结果。未配置时，运行会以 `failed` 停止，并给出诊断信息 `delegation was requested but no handler is configured`——即第 7 阶段的行为。

## 对真实应用进行验证

用桩实现替换 provider 后启动 API（在 `/tmp` 下写一个临时脚本，不要放进仓库），然后：

```sh
curl -s localhost:8000/tasks -H 'content-type: application/json' \
  -d '{"goal": "Calculate 2 + 2"}'
curl -s localhost:8000/tasks/<task_id>
curl -s localhost:8000/tasks/<task_id>/traces
```

分别排入一条高于推理阈值和一条低于该阈值的路由；第一步会报告 `policy_outcome: delegate_to_llm` 并以模型的文本作为其结果，第二步则正常执行。
