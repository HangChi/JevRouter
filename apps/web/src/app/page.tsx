import { connection } from "next/server";

import { createApiClient, readFromApi } from "@/lib/api";
import { Notice } from "@/components/Notice";
import { SubmitForm } from "@/components/SubmitForm";
import { TaskList } from "@/components/TaskList";

export default async function Home() {
  // The run list is the live state of another process, so rendering waits for a
  // request rather than being baked into a static shell.
  await connection();

  const result = await readFromApi(() => createApiClient().listTasks());

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-ink">Runs</h1>
        <p className="mt-1 text-sm text-ink-2">
          Every run the API knows about, newest first. The registry lives in the API process, so a
          restarted API starts this list empty.
        </p>
      </div>

      <SubmitForm />

      {result.ok ? (
        <TaskList tasks={result.value.tasks} />
      ) : (
        <Notice tone={result.unavailable ? "bad" : "neutral"} title="The run list could not be read">
          {result.message}
        </Notice>
      )}
    </div>
  );
}
