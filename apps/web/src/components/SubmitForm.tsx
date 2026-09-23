"use client";

import { useActionState, useState } from "react";

import { submitTaskAction, type ActionResult } from "@/actions/tasks";

const INITIAL: ActionResult = { ok: true };

/**
 * Submitting a goal is the one write the home page owns. The API validates the
 * goal, so a rejection it reports is shown verbatim rather than re-worded here.
 */
export function SubmitForm() {
  const [state, formAction, pending] = useActionState(submitTaskAction, INITIAL);
  const [context, setContext] = useState("");

  return (
    <form action={formAction} className="rounded-lg border border-hairline bg-surface p-4">
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium tracking-wide text-ink-2">Goal</span>
          <input
            name="goal"
            type="text"
            required
            maxLength={2000}
            placeholder="Calculate 2 + 2 and write the result to a note"
            className="rounded-md border border-hairline bg-page px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium tracking-wide text-ink-2">
            Context <span className="text-muted">(optional JSON object)</span>
          </span>
          <textarea
            name="context"
            rows={2}
            value={context}
            onChange={(event) => setContext(event.target.value)}
            placeholder='{"topic": "routing"}'
            className="rounded-md border border-hairline bg-page px-3 py-2 font-mono text-xs text-ink placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </label>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={pending}
            className="rounded-md bg-accent-strong px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {pending ? "Starting…" : "Start run"}
          </button>
          {state.ok ? null : (
            <p role="status" className="text-xs text-critical">
              {state.message}
            </p>
          )}
        </div>
      </div>
    </form>
  );
}
