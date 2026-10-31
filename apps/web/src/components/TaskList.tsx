import Link from "next/link";

import type { TaskSummary } from "@/lib/types";
import { isLiveStatus } from "@/lib/viewModel";
import { StatusBadge } from "./StatusBadge";

/** API 知道的运行，最新的在前，按 API 返回的样子展示。 */
export function TaskList({ tasks }: { tasks: TaskSummary[] }) {
  if (tasks.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-hairline px-4 py-8 text-center text-sm text-muted">
        还没有运行。在上方提交一个目标即可开始。
      </p>
    );
  }

  return (
    <ul className="divide-y divide-hairline overflow-hidden rounded-lg border border-hairline bg-surface">
      {tasks.map((task) => (
        <li key={task.task_id}>
          <Link
            href={`/tasks/${task.task_id}`}
            className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 transition-colors hover:bg-page"
          >
            <StatusBadge status={task.status} />
            <span className="min-w-0 flex-1 truncate text-sm text-ink">{task.goal}</span>
            {/* 进行中的句柄还没有步骤数：API 只在运行结束时才记录它，
                显示出来会被读成「一步都没走」。 */}
            {isLiveStatus(task.status) ? null : (
              <span className="font-mono text-xs tabular-nums text-ink-2">
                {task.step} 步
              </span>
            )}
            <span className="font-mono text-xs text-muted">{task.task_id.slice(0, 8)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
