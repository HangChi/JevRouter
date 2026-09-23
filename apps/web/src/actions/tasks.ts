"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError, ApiUnavailableError, createApiClient } from "@/lib/api";

export interface ActionResult {
  ok: boolean;
  message?: string;
}

function describe(error: unknown): string {
  if (error instanceof ApiError || error instanceof ApiUnavailableError) {
    return error.message;
  }
  return "the request failed for a reason the API did not explain";
}

/**
 * Start a run and land on its page.
 *
 * `redirect` throws, so it is deliberately outside the try: catching it would
 * turn a successful submit into a reported failure.
 */
export async function submitTaskAction(
  _previous: ActionResult | undefined,
  formData: FormData,
): Promise<ActionResult> {
  const goal = String(formData.get("goal") ?? "");
  const rawContext = String(formData.get("context") ?? "").trim();

  let context: Record<string, unknown> | undefined;
  if (rawContext !== "") {
    let parsed: unknown;
    try {
      parsed = JSON.parse(rawContext);
    } catch (error) {
      return { ok: false, message: `context is not valid JSON: ${(error as Error).message}` };
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return { ok: false, message: "context must be a JSON object" };
    }
    context = parsed as Record<string, unknown>;
  }

  let taskId: string;
  try {
    const created = await createApiClient().submitTask(goal, context);
    taskId = created.task_id;
  } catch (error) {
    return { ok: false, message: describe(error) };
  }

  revalidatePath("/");
  redirect(`/tasks/${taskId}`);
}

/** Answer a pending confirmation. A `409` means the run moved on without us. */
export async function confirmTaskAction(taskId: string, approved: boolean): Promise<ActionResult> {
  try {
    await createApiClient().confirmTask(taskId, approved);
  } catch (error) {
    return { ok: false, message: describe(error) };
  }
  revalidatePath(`/tasks/${taskId}`);
  return { ok: true };
}

/** Answer a pending question. A `409` means the run moved on without us. */
export async function provideInputAction(
  taskId: string,
  _previous: ActionResult | undefined,
  formData: FormData,
): Promise<ActionResult> {
  const answer = String(formData.get("answer") ?? "");
  try {
    await createApiClient().provideInput(taskId, answer);
  } catch (error) {
    return { ok: false, message: describe(error) };
  }
  revalidatePath(`/tasks/${taskId}`);
  return { ok: true };
}
