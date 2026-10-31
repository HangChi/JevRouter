"use client";

import { useActionState, useState } from "react";

import { submitTaskAction, type ActionResult } from "@/actions/tasks";

const INITIAL: ActionResult = { ok: true };

/**
 * 提交目标是首页拥有的唯一写入操作。目标由 API 校验，因此 API 报告的拒绝会原样
 * 展示，而不在这里重新措辞。
 */
export function SubmitForm() {
  const [state, formAction, pending] = useActionState(submitTaskAction, INITIAL);
  const [context, setContext] = useState("");

  return (
    <form action={formAction} className="rounded-lg border border-hairline bg-surface p-4">
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium tracking-wide text-ink-2">目标</span>
          <input
            name="goal"
            type="text"
            required
            maxLength={2000}
            placeholder="计算 6 * 7，然后把结果写进 notes.md"
            className="rounded-md border border-hairline bg-page px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium tracking-wide text-ink-2">
            上下文 <span className="text-muted">（可选，JSON 对象）</span>
          </span>
          <textarea
            name="context"
            rows={2}
            value={context}
            onChange={(event) => setContext(event.target.value)}
            placeholder='{"主题": "路由"}'
            className="rounded-md border border-hairline bg-page px-3 py-2 font-mono text-xs text-ink placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </label>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={pending}
            className="rounded-md bg-accent-strong px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {pending ? "启动中…" : "开始运行"}
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
