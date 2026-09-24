import { branchLabel, decisionChain, outcomeTone, type Tone } from "@/lib/viewModel";
import type { TraceView } from "@/lib/types";

const TONE_DOT: Record<Tone, string> = {
  neutral: "bg-muted",
  live: "bg-accent",
  blocked: "bg-warning",
  good: "bg-good",
  bad: "bg-critical",
};

/**
 * The run's steps in order, so the shape of a run is visible before any card is
 * read. Each node names its step, action and outcome; the branch is available on
 * hover and in full on the card itself.
 */
export function DecisionChain({ traces }: { traces: TraceView[] }) {
  const nodes = decisionChain(traces);
  if (nodes.length === 0) {
    return (
      <p className="text-xs text-muted">
        还没有已完成的步骤，因此没有决策链可画。
      </p>
    );
  }

  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-2">
      {nodes.map((node, index) => {
        const tone = outcomeTone(node.outcome);
        return (
          <li key={node.step} className="flex items-center gap-2">
            {index > 0 ? (
              <span className="font-mono text-xs text-muted" aria-hidden="true">
                →
              </span>
            ) : null}
            <span
              className="inline-flex items-center gap-2 rounded-full border border-hairline bg-surface px-2.5 py-1"
              title={branchLabel(node.branch)}
            >
              <span className="font-mono text-xs text-muted">{node.step}</span>
              <span className="font-mono text-xs text-ink">{node.action}</span>
              <span className={`h-2 w-2 rounded-full ${TONE_DOT[tone]}`} aria-hidden="true" />
            </span>
          </li>
        );
      })}
    </ol>
  );
}
