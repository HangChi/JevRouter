import type { Tone } from "@/lib/viewModel";

const TONE_BOX: Record<Tone, string> = {
  neutral: "border-hairline bg-page text-ink-2",
  live: "border-accent/40 bg-accent/10 text-ink",
  blocked: "border-warning/50 bg-warning/15 text-ink",
  good: "border-good/40 bg-good/10 text-ink",
  bad: "border-critical/40 bg-critical/10 text-ink",
};

/**
 * A message the operator has to see before reading the data: the API could not
 * be reached, a run carried a diagnostic, or an answer arrived too late. A
 * connection failure names the upstream so a misconfigured dashboard is obvious
 * rather than looking like an empty system.
 */
export function Notice({
  tone = "neutral",
  title,
  children,
}: {
  tone?: Tone;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm ${TONE_BOX[tone]}`} role="status">
      <p className="font-medium">{title}</p>
      {children === undefined ? null : <div className="mt-1 text-xs">{children}</div>}
    </div>
  );
}
