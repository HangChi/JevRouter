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
 * 启动一次运行并跳转到它的页面。
 *
 * `redirect` 会抛异常，所以它被刻意放在 try 之外：把它捕获会把一次成功的提交
 * 变成一次被报告的失败。
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

/** 回应一次待确认。`409` 表示这次运行已经自己往下走了，我们手上的批准作废。 */
export async function confirmTaskAction(
  taskId: string,
  approved: boolean,
  digest: string,
): Promise<ActionResult> {
  try {
    await createApiClient().confirmTask(taskId, approved, digest);
  } catch (error) {
    return { ok: false, message: describe(error) };
  }
  revalidatePath(`/tasks/${taskId}`);
  return { ok: true };
}

/** 回答一次待确认的问题。`409` 表示这次运行已经自己往下走了。 */
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
