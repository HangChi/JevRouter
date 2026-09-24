import { formatDuration, formatTokens, outcomeAction, type ComparisonRow } from "@/lib/viewModel";

const CELL = "px-3 py-2 align-top text-xs";

/** What one router did with one case, as one table cell. */
function RouterCell({ outcome }: { outcome: ComparisonRow["jev"] }) {
  if (outcome === null) {
    return <span className="font-mono text-muted">—</span>;
  }
  const failed = outcome.action === null;
  return (
    <div className="flex flex-col gap-0.5">
      <span className={`font-mono ${failed ? "text-critical" : "text-ink"}`}>
        {outcomeAction(outcome)}
      </span>
      {failed ? null : (
        <span className="font-mono text-muted tabular-nums">
          {formatDuration(outcome.latency_ms)} · {formatTokens(outcome.input_tokens, outcome.output_tokens)} tok
        </span>
      )}
    </div>
  );
}

function AgreementCell({ agreed }: { agreed: boolean | null }) {
  if (agreed === null) {
    return <span className="font-mono text-muted">—</span>;
  }
  return (
    <span className={agreed ? "font-mono text-good" : "font-mono text-warning"}>
      {agreed ? "same" : "differs"}
    </span>
  );
}

/**
 * One row per case, both routers side by side.
 *
 * A router that errored shows its error instead of an action, and agreement is
 * left blank: an error is not a disagreement, and counting it as one would
 * understate the agreement rate the cards above report.
 */
export function ComparisonTable({ rows }: { rows: ComparisonRow[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-hairline bg-surface">
      <table className="w-full min-w-[52rem] border-collapse">
        <thead>
          <tr className="border-b border-hairline text-left text-[0.65rem] tracking-widest text-muted uppercase">
            <th className={CELL}>Case</th>
            <th className={CELL}>Expected</th>
            <th className={CELL}>Jev</th>
            <th className={CELL}>LLM</th>
            <th className={CELL}>Route</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {rows.map((row) => (
            <tr key={row.caseId}>
              <td className={CELL}>
                <span className="font-mono text-ink">{row.caseId}</span>
                <span className="mt-0.5 block max-w-[18rem] truncate text-ink-2" title={row.goal}>
                  {row.goal}
                </span>
              </td>
              <td className={`${CELL} font-mono text-ink-2`}>{row.expectedAction}</td>
              <td className={CELL}>
                <RouterCell outcome={row.jev} />
              </td>
              <td className={CELL}>
                <RouterCell outcome={row.llm} />
              </td>
              <td className={CELL}>
                <AgreementCell agreed={row.agreed} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
