import { connection } from "next/server";

import { createApiClient, readFromApi } from "@/lib/api";
import { Notice } from "@/components/Notice";
import { SubmitForm } from "@/components/SubmitForm";
import { TaskList } from "@/components/TaskList";

export default async function Home() {
  // 运行列表是另一个进程的实时状态，因此渲染要等到请求到来，而不是被固化进
  // 一个静态骨架里。
  await connection();

  const result = await readFromApi(() => createApiClient().listTasks());

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-ink">运行</h1>
        <p className="mt-1 text-sm text-ink-2">
          API 知道的所有运行，最新在前。工具注册表存在于 API 进程内，因此 API 重启后这个列表会从空开始。
        </p>
      </div>

      <SubmitForm />

      {result.ok ? (
        <TaskList tasks={result.value.tasks} />
      ) : (
        <Notice tone={result.unavailable ? "bad" : "neutral"} title="无法读取运行列表">
          {result.message}
        </Notice>
      )}
    </div>
  );
}
