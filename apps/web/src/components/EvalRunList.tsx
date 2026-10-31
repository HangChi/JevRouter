import Link from "next/link";

import type { EvalRunSummary } from "@/lib/types";

/**
 * 已记录的评测运行，最新的在前，完全按 API 返回的样子展示。
 *
 * 一次运行是一条已完成的记录而不是一个正在进行的进程，因此没有什么需要轮询，
 * 也没有状态可显示：模式和用例数就说明了这次运行是什么。
 */
export function EvalRunList({ runs }: { runs: EvalRunSummary[] }) {
  if (runs.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-hairline px-4 py-8 text-center text-sm text-muted">
        还没有记录过 eval 运行。执行{" "}
        <code className="font-mono text-ink-2">uv run python -m evals --mode compare</code> 并用{" "}
        <code className="font-mono text-ink-2">--api</code> 投递。
      </p>
    );
  }

  return (
    <ul className="divide-y divide-hairline overflow-hidden rounded-lg border border-hairline bg-surface">
      {runs.map((run) => (
        <li key={run.run_id}>
          <Link
            href={`/evals/${run.run_id}`}
            className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 transition-colors hover:bg-page"
          >
            <span className="rounded-full border border-hairline bg-page px-2.5 py-1 text-xs font-medium tracking-wide text-ink">
              {run.mode.replace(/_/g, " ")}
            </span>
            <span className="font-mono text-xs text-muted">{run.created_at}</span>
            <span className="ml-auto font-mono text-xs tabular-nums text-ink-2">
              {run.case_count} 个用例
            </span>
            <span className="font-mono text-xs text-muted">{run.run_id.slice(0, 8)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
