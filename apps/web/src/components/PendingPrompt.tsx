"use client";

import { useActionState, useState, useTransition } from "react";

import { confirmTaskAction, provideInputAction, type ActionResult } from "@/actions/tasks";
import type { TaskView } from "@/lib/types";
import { JsonBlock } from "./JsonBlock";

const INITIAL: ActionResult = { ok: true };

function InputPrompt({ taskId, question }: { taskId: string; question: string }) {
  const [state, formAction, pending] = useActionState(
    provideInputAction.bind(null, taskId),
    INITIAL,
  );

  return (
    <form action={formAction} className="flex flex-col gap-3">
      <p className="text-sm text-ink">{question}</p>
      <div className="flex flex-wrap items-center gap-3">
        <input
          name="answer"
          type="text"
          required
          maxLength={4000}
          autoFocus
          placeholder="Type the answer the run is waiting for"
          className="min-w-0 flex-1 rounded-md border border-hairline bg-page px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none"
        />
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-accent-strong px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {pending ? "Sending…" : "Send answer"}
        </button>
      </div>
      {state.ok ? null : (
        <p role="status" className="text-xs text-critical">
          {state.message}
        </p>
      )}
    </form>
  );
}

function ConfirmationPrompt({
  taskId,
  action,
  args,
}: {
  taskId: string;
  action: string;
  args: unknown;
}) {
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);

  const answer = (approved: boolean) => {
    startTransition(async () => {
      const result = await confirmTaskAction(taskId, approved);
      setMessage(result.ok ? null : (result.message ?? "the answer was not accepted"));
    });
  };

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink">
        The run is waiting to execute <span className="font-mono text-ink">{action}</span> with the
        arguments below.
      </p>
      <JsonBlock label="Arguments to be executed" value={args} defaultOpen />
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={pending}
          onClick={() => answer(true)}
          className="rounded-md bg-accent-strong px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {pending ? "Answering…" : "Approve"}
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={() => answer(false)}
          className="rounded-md border border-hairline bg-surface px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-page disabled:opacity-50"
        >
          Deny
        </button>
        {message === null ? null : (
          <p role="status" className="text-xs text-critical">
            {message}
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * The one thing only a human can do. The run is parked mid-step, so the prompt
 * carries the action and its resolved arguments: approving is approving exactly
 * what will run, not just the action's name.
 */
export function PendingPrompt({ task }: { task: TaskView }) {
  const confirmation = task.pending_confirmation;
  if (confirmation !== null) {
    return (
      <ConfirmationPrompt
        taskId={task.task_id}
        action={confirmation.action}
        args={confirmation.arguments}
      />
    );
  }

  const input = task.pending_input;
  if (input !== null) {
    return <InputPrompt taskId={task.task_id} question={input.question} />;
  }

  return null;
}
