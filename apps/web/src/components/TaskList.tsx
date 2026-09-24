import Link from "next/link";

import type { TaskSummary } from "@/lib/types";
import { isLiveStatus } from "@/lib/viewModel";
import { StatusBadge } from "./StatusBadge";

/** The runs the API knows about, newest first, as the API returns them. */
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
            {/* A live handle has no step count yet: the API only records it when
                the run finishes, so showing it would read as "no steps taken". */}
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
