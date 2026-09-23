import Link from "next/link";
import { connection } from "next/server";
import { notFound } from "next/navigation";

import { createApiClient, readFromApi } from "@/lib/api";
import { DecisionChain } from "@/components/DecisionChain";
import { LiveRefresh } from "@/components/LiveRefresh";
import { Notice } from "@/components/Notice";
import { PendingPrompt } from "@/components/PendingPrompt";
import { StatusBadge } from "@/components/StatusBadge";
import { StepCard } from "@/components/StepCard";
import { isLiveStatus } from "@/lib/viewModel";

export default async function TaskPage({ params }: PageProps<"/tasks/[taskId]">) {
  const { taskId } = await params;
  await connection();

  const client = createApiClient();
  const task = await readFromApi(() => client.getTask(taskId));
  const traces = await readFromApi(() => client.getTraces(taskId));

  if (!task.ok) {
    if (task.unavailable) {
      return (
        <div className="flex flex-col gap-4">
          <BackLink />
          <Notice tone="bad" title="The API could not be reached">
            {task.message}
          </Notice>
        </div>
      );
    }
    // The API answered and does not know this task.
    notFound();
  }

  const view = task.value;
  const steps = traces.ok ? traces.value.traces : [];
  const live = isLiveStatus(view.status);

  return (
    <div className="flex flex-col gap-6">
      <BackLink />

      <section className="flex flex-col gap-3 rounded-lg border border-hairline bg-surface px-4 py-4">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <StatusBadge status={view.status} />
          <LiveRefresh active={live} />
          {/* Counted from the traces this page renders: the handle's own step
              counter is only recorded once the run finishes. */}
          <span className="ml-auto font-mono text-xs tabular-nums text-ink-2">
            {steps.length} {steps.length === 1 ? "step" : "steps"} recorded
          </span>
        </div>
        <h1 className="text-base font-semibold text-ink">{view.goal}</h1>
        <p className="font-mono text-xs text-muted">{view.task_id}</p>
        {view.diagnostic === null ? null : (
          <Notice tone="bad" title="Diagnostic">
            {view.diagnostic}
          </Notice>
        )}
      </section>

      {view.pending_confirmation !== null || view.pending_input !== null ? (
        <section className="flex flex-col gap-3 rounded-lg border border-warning/50 bg-warning/10 px-4 py-4">
          <h2 className="text-[0.7rem] font-semibold tracking-widest text-muted uppercase">
            Waiting for you
          </h2>
          <PendingPrompt task={view} />
        </section>
      ) : null}

      <section className="flex flex-col gap-3">
        <h2 className="text-[0.7rem] font-semibold tracking-widest text-muted uppercase">
          Decision chain
        </h2>
        <DecisionChain traces={steps} />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-[0.7rem] font-semibold tracking-widest text-muted uppercase">
          Steps
        </h2>
        {traces.ok ? null : (
          <Notice tone="bad" title="The traces could not be read">
            {traces.message}
          </Notice>
        )}
        {steps.length === 0 ? (
          <p className="rounded-lg border border-dashed border-hairline px-4 py-8 text-center text-sm text-muted">
            No step has completed yet.
          </p>
        ) : (
          <div className="flex flex-col gap-4">
            {steps.map((trace) => (
              <StepCard key={trace.step} trace={trace} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/" className="text-xs text-ink-2 transition-colors hover:text-ink">
      ← All runs
    </Link>
  );
}
