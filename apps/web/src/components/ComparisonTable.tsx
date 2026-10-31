import { formatDuration, formatTokens, outcomeAction, type ComparisonRow } from "@/lib/viewModel";

const CELL = "px-3 py-2 align-top text-xs";

/** 一个路由层对一个用例做了什么，作为一个表格单元格。 */
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
      {agreed ? "一致" : "分歧"}
    </span>
  );
}

/**
 * 每个用例一行，两个路由层并排。
 *
 * 出错的路由层显示它的错误而不是动作，一致性留空：错误不算分歧，把它算成分歧
 * 会低估上方卡片报告的一致率。
 */
export function ComparisonTable({ rows }: { rows: ComparisonRow[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-hairline bg-surface">
      <table className="w-full min-w-[52rem] border-collapse">
        <thead>
          <tr className="border-b border-hairline text-left text-[0.65rem] tracking-widest text-muted uppercase">
            <th className={CELL}>用例</th>
            <th className={CELL}>期望动作</th>
            <th className={CELL}>Jev</th>
            <th className={CELL}>LLM</th>
            <th className={CELL}>一致性</th>
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
