"use client";

import { useActionState, useState, useTransition } from "react";

import { confirmTaskAction, provideInputAction, type ActionResult } from "@/actions/tasks";
import type { TaskView } from "@/lib/types";
import { JsonBlock } from "./JsonBlock";

const INITIAL: ActionResult = { ok: true };

/** 把一个 ISO 时间显示成本地可读的时刻；解析不了就原样回显。 */
function formatDeadline(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("zh-CN", { hour12: false });
}

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
          placeholder="输入运行正在等待的答案"
          className="min-w-0 flex-1 rounded-md border border-hairline bg-page px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none"
        />
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-accent-strong px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {pending ? "发送中…" : "发送"}
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
  digest,
  expiresAt,
}: {
  taskId: string;
  action: string;
  args: unknown;
  digest: string;
  expiresAt: string;
}) {
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);

  const answer = (approved: boolean) => {
    startTransition(async () => {
      const result = await confirmTaskAction(taskId, approved, digest);
      setMessage(result.ok ? null : (result.message ?? "应答未被接受"));
    });
  };

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink">
        运行即将执行 <span className="font-mono text-ink">{action}</span>，参数如下。
      </p>
      <JsonBlock label="待执行参数" value={args} defaultOpen />
      <p className="text-xs text-muted">
        这次批准只对上面这份参数有效，有效期至 {formatDeadline(expiresAt)}。
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={pending}
          onClick={() => answer(true)}
          className="rounded-md bg-accent-strong px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {pending ? "处理中…" : "批准"}
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={() => answer(false)}
          className="rounded-md border border-hairline bg-surface px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-page disabled:opacity-50"
        >
          拒绝
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
 * 只有人能做的这一件事。运行正停在步骤中间，因此提示里带着动作和它的实际参数：
 * 批准就是批准即将执行的这份东西，而不只是动作的名字。
 */
export function PendingPrompt({ task }: { task: TaskView }) {
  const confirmation = task.pending_confirmation;
  if (confirmation !== null) {
    return (
      <ConfirmationPrompt
        taskId={task.task_id}
        action={confirmation.action}
        args={confirmation.arguments}
        digest={confirmation.digest}
        expiresAt={confirmation.expires_at}
      />
    );
  }

  const input = task.pending_input;
  if (input !== null) {
    return <InputPrompt taskId={task.task_id} question={input.question} />;
  }

  return null;
}
