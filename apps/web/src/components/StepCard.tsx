import {
  ABSENT,
  branchLabel,
  completionMeter,
  formatDuration,
  outcomeLabel,
  outcomeTone,
  policyBranch,
  probabilityMeters,
  scoreReadouts,
  verificationReadout,
  type Tone,
} from "@/lib/viewModel";
import type { TraceView } from "@/lib/types";
import { JsonBlock } from "./JsonBlock";
import { ProbabilityMeter } from "./ProbabilityMeter";
import { ScoreReadout } from "./ScoreReadout";

const TONE_CHIP: Record<Tone, string> = {
  neutral: "border-hairline bg-muted/10 text-ink",
  live: "border-accent/40 bg-accent/10 text-ink",
  blocked: "border-warning/50 bg-warning/15 text-ink",
  good: "border-good/40 bg-good/10 text-ink",
  bad: "border-critical/40 bg-critical/10 text-ink",
};

const TONE_DOT: Record<Tone, string> = {
  neutral: "bg-muted",
  live: "bg-accent",
  blocked: "bg-warning",
  good: "bg-good",
  bad: "bg-critical",
};

function SectionHeading({ children }: { children: string }) {
  return (
    <h3 className="text-[0.7rem] font-semibold tracking-widest text-muted uppercase">
      {children}
    </h3>
  );
}

/**
 * One step's decision graph: the signals Jev returned, the control outcome the
 * Policy Engine chose from them, what the step then did, and what the Verifier
 * made of it. Every value shown is a field of the API's `TraceView` — nothing is
 * interpolated, and a field the API did not return renders as a dash.
 */
export function StepCard({ trace }: { trace: TraceView }) {
  const meters = probabilityMeters(trace);
  const scores = scoreReadouts(trace);
  const risk = scores.find((readout) => readout.key === "route_risk");
  const quality = scores.find((readout) => readout.key === "quality_score");
  const completion = completionMeter(trace);
  const verification = verificationReadout(trace);
  const branch = policyBranch(trace);
  const outcome = trace.policy_outcome;
  const tone = outcomeTone(outcome);

  return (
    <article className="rounded-lg border border-hairline bg-surface">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-hairline px-4 py-3">
        <span className="font-mono text-xs text-muted">step {trace.step}</span>
        <span className="font-mono text-sm font-semibold text-ink">{trace.action}</span>
        <span className="ml-auto flex items-center gap-3">
          <span
            className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium ${TONE_CHIP[tone]}`}
          >
            <span className={`h-2 w-2 rounded-full ${TONE_DOT[tone]}`} aria-hidden="true" />
            {outcomeLabel(outcome)}
          </span>
          <span className="font-mono text-xs tabular-nums text-ink-2">
            {formatDuration(trace.duration_ms)}
          </span>
        </span>
      </header>
      {trace.confirmed === null ? null : (
        <p className="border-b border-hairline px-4 py-2 text-xs text-muted">
          This step waited for a human, so its duration includes that wait.
        </p>
      )}

      <div className="grid gap-6 px-4 py-4 md:grid-cols-2">
        <section>
          <SectionHeading>Jev signals</SectionHeading>
          <div className="mt-3 space-y-2">
            {meters.map((meter) => (
              <ProbabilityMeter key={meter.key} meter={meter} />
            ))}
            {risk === undefined ? null : <ScoreReadout key={risk.key} readout={risk} />}
            {meters.length === 0 && risk === undefined ? (
              <p className="text-xs text-muted">
                The API returned no routing signals for this step.
              </p>
            ) : null}
          </div>
        </section>

        <section>
          <SectionHeading>Policy</SectionHeading>
          <p className="mt-3 text-sm text-ink">
            {outcomeLabel(outcome)}
            <span className="text-muted"> — </span>
            <span className="text-ink-2">{trace.policy_reason ?? ABSENT}</span>
          </p>

          <SectionHeading>Branch</SectionHeading>
          <p className="mt-2 text-sm text-ink">
            {branchLabel(branch)}
            {trace.confirmed === true && trace.executed ? (
              <span className="text-muted"> (after confirmation)</span>
            ) : null}
          </p>

          <SectionHeading>Verification</SectionHeading>
          <div className="mt-3 space-y-2">
            {completion === null ? (
              <p className="text-xs text-muted">This step was not verified.</p>
            ) : (
              <>
                <ProbabilityMeter meter={completion} />
                {verification?.completionMet ? null : (
                  <p className="text-xs text-ink-2">
                    Below the runner&rsquo;s threshold, so the run kept routing.
                  </p>
                )}
              </>
            )}
            {quality === undefined ? null : <ScoreReadout key={quality.key} readout={quality} />}
          </div>
        </section>
      </div>

      <footer className="flex flex-col gap-2 border-t border-hairline px-4 py-3">
        {trace.arguments === undefined || trace.arguments === null ? null : (
          <JsonBlock label="Arguments" value={trace.arguments} />
        )}
        {trace.executed ? (
          <JsonBlock label="Result" value={trace.result} defaultOpen />
        ) : (
          <p className="text-xs text-muted">No tool ran for this step.</p>
        )}
        <JsonBlock label="State snapshot" value={trace.state_snapshot} />
      </footer>
    </article>
  );
}
