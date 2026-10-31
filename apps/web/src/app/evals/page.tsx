import { connection } from "next/server";

import { createApiClient, readFromApi } from "@/lib/api";
import { EvalRunList } from "@/components/EvalRunList";
import { MetricCard } from "@/components/MetricCard";
import { MetricCards } from "@/components/MetricCards";
import { Notice } from "@/components/Notice";
import { agreementCard, comparisonCardSets } from "@/lib/viewModel";

export default async function EvalsPage() {
  // 运行列表是另一个进程的状态，因此渲染要等到请求到来，而不是被固化进一个
  // 静态骨架里。
  await connection();

  const result = await readFromApi(() => createApiClient().listEvalRuns());
  const newest = result.ok ? result.value.runs[0] : undefined;
  const detail =
    newest === undefined
      ? undefined
      : await readFromApi(() => createApiClient().getEvalRun(newest.run_id));

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-ink">评测</h1>
        <p className="mt-1 text-sm text-ink-2">
          Jev 与 LLM 基线在固定用例集上的对比。运行由 eval CLI 记录，这个页面本身不会启动任何评测。
        </p>
      </div>

      {result.ok ? null : (
        <Notice tone={result.unavailable ? "bad" : "neutral"} title="无法读取评测列表">
          {result.message}
        </Notice>
      )}

      {detail !== undefined && !detail.ok ? (
        <Notice tone={detail.unavailable ? "bad" : "neutral"} title="无法读取最新一次运行">
          {detail.message}
        </Notice>
      ) : null}

      {detail !== undefined && detail.ok ? (
        <section className="flex flex-col gap-4">
          <h2 className="text-[0.7rem] font-semibold tracking-widest text-muted uppercase">
            最新一次 · {detail.value.mode} · {detail.value.case_count} 个用例
          </h2>
          {(() => {
            const agreement = agreementCard(detail.value.metrics);
            if (agreement === null) {
              return null;
            }
            return (
              <div className="max-w-xs">
                <MetricCard card={agreement} />
              </div>
            );
          })()}
          {comparisonCardSets(detail.value.metrics).map((set) => (
            <MetricCards key={set.mode} set={set} />
          ))}
        </section>
      ) : null}

      <section className="flex flex-col gap-3">
        <h2 className="text-[0.7rem] font-semibold tracking-widest text-muted uppercase">
          已记录的运行
        </h2>
        {result.ok ? <EvalRunList runs={result.value.runs} /> : null}
      </section>
    </div>
  );
}
