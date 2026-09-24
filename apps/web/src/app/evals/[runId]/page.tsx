import Link from "next/link";
import { connection } from "next/server";
import { notFound } from "next/navigation";

import { createApiClient, readFromApi } from "@/lib/api";
import { ComparisonTable } from "@/components/ComparisonTable";
import { MetricCard } from "@/components/MetricCard";
import { MetricCards } from "@/components/MetricCards";
import { Notice } from "@/components/Notice";
import { agreementCard, comparisonCardSets, comparisonRows } from "@/lib/viewModel";

export default async function EvalRunPage({ params }: PageProps<"/evals/[runId]">) {
  const { runId } = await params;
  await connection();

  const result = await readFromApi(() => createApiClient().getEvalRun(runId));

  if (!result.ok) {
    if (result.unavailable) {
      return (
        <div className="flex flex-col gap-4">
          <BackLink />
          <Notice tone="bad" title="The API could not be reached">
            {result.message}
          </Notice>
        </div>
      );
    }
    // The API answered and does not know this run id.
    notFound();
  }

  const view = result.value;
  const rows = comparisonRows(view.outcomes);
  const agreement = agreementCard(view.metrics);

  return (
    <div className="flex flex-col gap-6">
      <BackLink />

      <section className="flex flex-col gap-3 rounded-lg border border-hairline bg-surface px-4 py-4">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="rounded-full border border-hairline bg-page px-2.5 py-1 text-xs font-medium tracking-wide text-ink">
            {view.mode.replace(/_/g, " ")}
          </span>
          <span className="font-mono text-xs tabular-nums text-ink-2">
            {view.case_count} {view.case_count === 1 ? "case" : "cases"}
          </span>
          <span className="font-mono text-xs text-muted">{view.created_at}</span>
        </div>
        <h1 className="text-base font-semibold text-ink">Routing comparison</h1>
        <p className="font-mono text-xs text-muted">{view.run_id}</p>
        {agreement === null ? null : (
          <div className="max-w-xs">
            <MetricCard card={agreement} />
          </div>
        )}
      </section>

      <section className="flex flex-col gap-4">
        {comparisonCardSets(view.metrics).map((set) => (
          <MetricCards key={set.mode} set={set} />
        ))}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-[0.7rem] font-semibold tracking-widest text-muted uppercase">
          Cases
        </h2>
        <ComparisonTable rows={rows} />
      </section>
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/evals" className="text-xs text-ink-2 transition-colors hover:text-ink">
      ← All eval runs
    </Link>
  );
}
