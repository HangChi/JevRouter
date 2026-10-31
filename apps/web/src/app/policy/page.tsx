import { connection } from "next/server";

import { Notice } from "@/components/Notice";
import { createApiClient, readFromApi } from "@/lib/api";
import type { PolicyView } from "@/lib/types";

/** 一个阈值的一行：名字、数值、以及它跨过之后会发生什么。 */
function ThresholdRow({
  label,
  value,
  effect,
  fraction,
}: {
  label: string;
  value: string;
  effect: string;
  /** 0..1 之间的相对位置，用来画一条背景条；undefined 表示不适用。 */
  fraction?: number;
}) {
  return (
    <div className="rounded-md border border-hairline bg-surface px-3 py-2.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs font-medium text-ink">{label}</span>
        <span className="font-mono text-sm tabular-nums text-ink">{value}</span>
      </div>
      {fraction === undefined ? null : (
        <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-page">
          <div
            className="h-full rounded-full bg-accent"
            style={{ width: `${Math.round(Math.min(1, Math.max(0, fraction)) * 100)}%` }}
          />
        </div>
      )}
      <p className="mt-1 text-xs text-ink-2">{effect}</p>
    </div>
  );
}

const RISK_LABEL: Record<string, string> = {
  read: "读取",
  write: "写入",
  external: "外部副作用",
};

function PolicyBody({ policy }: { policy: PolicyView }) {
  const t = policy.thresholds;
  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-3">
        <h2 className="text-[0.7rem] font-semibold tracking-widest text-muted uppercase">
          确认
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <ThresholdRow
            label="确认概率阈值"
            value={t.confirmation.toFixed(2)}
            fraction={t.confirmation}
            effect="高于它 → 停下来等人工批准。工具声明为写入或外部副作用时，无论概率多少都必须确认。"
          />
          <ThresholdRow
            label="风险分阈值"
            value={t.risk.toFixed(1)}
            fraction={t.risk / 4}
            effect="风险分达到它 → 停下来等人工批准。模型给低分也不能绕过工具自身的风险等级。"
          />
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-[0.7rem] font-semibold tracking-widest text-muted uppercase">
          委托与执行
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <ThresholdRow
            label="推理需求阈值"
            value={t.reasoning.toFixed(2)}
            fraction={t.reasoning}
            effect="高于它 → 这一步交给 LLM 处理，而不是由 Jev 直接选动作。"
          />
          <ThresholdRow
            label="动作置信度阈值"
            value={t.confidence.toFixed(2)}
            fraction={t.confidence}
            effect="低于它 → 同样交给 LLM。调低它会让更多步骤自动执行，也会放大选错动作的代价。"
          />
          <ThresholdRow
            label="完成度阈值"
            value={t.completion.toFixed(2)}
            fraction={t.completion}
            effect="验证器给出的完成概率达到它 → 结束任务；否则回到路由层继续下一步。"
          />
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-[0.7rem] font-semibold tracking-widest text-muted uppercase">
          工具与副作用等级
        </h2>
        <div className="overflow-hidden rounded-lg border border-hairline">
          <table className="w-full text-left text-xs">
            <thead className="bg-page text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">工具</th>
                <th className="px-3 py-2 font-medium">等级</th>
                <th className="px-3 py-2 font-medium">必须确认</th>
                <th className="px-3 py-2 font-medium">说明</th>
              </tr>
            </thead>
            <tbody>
              {policy.tools.map((tool) => (
                <tr key={tool.name} className="border-t border-hairline">
                  <td className="px-3 py-2 font-mono text-ink">{tool.name}</td>
                  <td className="px-3 py-2 text-ink-2">{RISK_LABEL[tool.risk] ?? tool.risk}</td>
                  <td className="px-3 py-2">
                    {tool.requires_confirmation ? (
                      <span className="text-warning">是</span>
                    ) : (
                      <span className="text-muted">否</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-ink-2">{tool.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <p className="text-xs text-ink-2">
        一次批准绑定在 <span className="font-mono">{policy.confirmation_binding}</span> 上，
        有效期 {Math.round(policy.confirmation_ttl_seconds / 60)} 分钟；参数一变，旧的批准立即失效。
      </p>
    </div>
  );
}

export default async function PolicyPage() {
  await connection();

  const result = await readFromApi(() => createApiClient().getPolicy());

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-ink">策略</h1>
        <p className="mt-1 text-sm text-ink-2">
          这里显示的是 API 进程里真正生效的阈值，不是文档里的示例值。它们是项目初值而非服务商推荐值，
          应当由评测数据校准：
          <span className="ml-1 font-mono text-ink">
            python -m evals --mode calibrate --from-report &lt;报告&gt;
          </span>
        </p>
      </div>

      {result.ok ? (
        <PolicyBody policy={result.value} />
      ) : (
        <Notice tone={result.unavailable ? "bad" : "neutral"} title="无法读取当前策略">
          {result.message}
        </Notice>
      )}
    </div>
  );
}
