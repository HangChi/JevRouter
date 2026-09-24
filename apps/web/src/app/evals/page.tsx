import { connection } from "next/server";

import { createApiClient, readFromApi } from "@/lib/api";
import { EvalRunList } from "@/components/EvalRunList";
import { MetricCard } from "@/components/MetricCard";
import { MetricCards } from "@/components/MetricCards";
import { Notice } from "@/components/Notice";
import { agreementCard, comparisonCardSets } from "@/lib/viewModel";

export default async function EvalsPage() {
  // The run list is another process's state, so rendering waits for a request
  // rather than being baked into a static shell.
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
        <h1 className="text-lg font-semibold tracking-tight text-ink">Evals</h1>
        <p className="mt-1 text-sm text-ink-2">
          Jev against the LLM baseline over the fixed case set. A run is recorded by the eval CLI;
          nothing on this page starts one.
        </p>
      </div>

      {result.ok ? null : (
        <Notice tone={result.unavailable ? "bad" : "neutral"} title="The eval list could not be read">
          {result.message}
        </Notice>
      )}

      {detail !== undefined && !detail.ok ? (
        <Notice tone={detail.unavailable ? "bad" : "neutral"} title="The newest run could not be read">
          {detail.message}
        </Notice>
      ) : null}

      {detail !== undefined && detail.ok ? (
        <section className="flex flex-col gap-4">
          <h2 className="text-[0.7rem] font-semibold tracking-widest text-muted uppercase">
            Newest run · {detail.value.mode} · {detail.value.case_count} cases
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
          Recorded runs
        </h2>
        {result.ok ? <EvalRunList runs={result.value.runs} /> : null}
      </section>
    </div>
  );
}
