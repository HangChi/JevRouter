import Link from "next/link";

import type { EvalRunSummary } from "@/lib/types";

/**
 * The recorded eval runs, newest first, exactly as the API returns them.
 *
 * A run is a finished record rather than a live process, so there is nothing to
 * poll and no status to show: the mode and the case count say what the run was.
 */
export function EvalRunList({ runs }: { runs: EvalRunSummary[] }) {
  if (runs.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-hairline px-4 py-8 text-center text-sm text-muted">
        No eval run recorded yet. Run{" "}
        <code className="font-mono text-ink-2">uv run python -m evals --mode compare</code> and post
        it with <code className="font-mono text-ink-2">--api</code>.
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
              {run.case_count} {run.case_count === 1 ? "case" : "cases"}
            </span>
            <span className="font-mono text-xs text-muted">{run.run_id.slice(0, 8)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
