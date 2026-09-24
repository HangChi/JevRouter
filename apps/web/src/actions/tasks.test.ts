import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, ApiUnavailableError, type ApiClient } from "@/lib/api";
import { apiClientStub } from "@/test/support";
import { confirmTaskAction, provideInputAction, submitTaskAction } from "./tasks";

const { createApiClient, revalidatePath } = vi.hoisted(() => ({
  createApiClient: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath }));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Error(`redirect:${to}`);
  },
  notFound: () => {
    throw new Error("notFound");
  },
}));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, createApiClient };
});

beforeEach(() => {
  vi.clearAllMocks();
});

function stub(overrides: Partial<ApiClient>): void {
  createApiClient.mockReturnValue(apiClientStub(overrides));
}

function formData(entries: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(entries)) {
    data.set(key, value);
  }
  return data;
}

describe("submitTaskAction", () => {
  it("submits the goal and lands on the new run's page", async () => {
    const submitTask = vi.fn(async () => ({ task_id: "abc123", status: "running" }));
    stub({ submitTask });

    await expect(
      submitTaskAction(undefined, formData({ goal: "计算 6 * 7" })),
    ).rejects.toThrow("redirect:/tasks/abc123");
    expect(submitTask).toHaveBeenCalledWith("计算 6 * 7", undefined);
    expect(revalidatePath).toHaveBeenCalledWith("/");
  });

  it("passes no context when the field is left empty", async () => {
    const submitTask = vi.fn(async () => ({ task_id: "t", status: "running" }));
    stub({ submitTask });

    await expect(
      submitTaskAction(undefined, formData({ goal: "g", context: "   " })),
    ).rejects.toThrow("redirect:/tasks/t");
    expect(submitTask).toHaveBeenCalledWith("g", undefined);
  });

  it("submits a context that is a JSON object", async () => {
    const submitTask = vi.fn(async () => ({ task_id: "t", status: "running" }));
    stub({ submitTask });

    await expect(
      submitTaskAction(undefined, formData({ goal: "g", context: '{"主题": "路由"}' })),
    ).rejects.toThrow("redirect:/tasks/t");
    expect(submitTask).toHaveBeenCalledWith("g", { 主题: "路由" });
  });

  it("refuses a context that is not JSON before asking the API", async () => {
    const submitTask = vi.fn(async () => ({ task_id: "t", status: "running" }));
    stub({ submitTask });

    const result = await submitTaskAction(
      undefined,
      formData({ goal: "g", context: "{主题}" }),
    );

    expect(result.ok).toBe(false);
    expect(result.message).toMatch(/^context is not valid JSON:/);
    expect(submitTask).not.toHaveBeenCalled();
  });

  it("refuses a context that is not an object", async () => {
    const submitTask = vi.fn(async () => ({ task_id: "t", status: "running" }));
    stub({ submitTask });

    for (const context of ["[1, 2]", '"just a string"', "5"]) {
      const result = await submitTaskAction(
        undefined,
        formData({ goal: "g", context }),
      );
      expect(result).toEqual({ ok: false, message: "context must be a JSON object" });
    }
    expect(submitTask).not.toHaveBeenCalled();
  });

  it("reports a rejection from the API in the API's own words", async () => {
    const submitTask = vi.fn(async () => {
      throw new ApiError(422, "goal must not be blank");
    });
    stub({ submitTask });

    const result = await submitTaskAction(undefined, formData({ goal: "" }));

    expect(result).toEqual({ ok: false, message: "goal must not be blank" });
    expect(revalidatePath).not.toHaveBeenCalled();
  });

  it("names the upstream when it cannot be reached at all", async () => {
    const submitTask = vi.fn(async () => {
      throw new ApiUnavailableError("http://127.0.0.1:8000", "connect ECONNREFUSED");
    });
    stub({ submitTask });

    const result = await submitTaskAction(undefined, formData({ goal: "g" }));

    expect(result.ok).toBe(false);
    expect(result.message).toContain("http://127.0.0.1:8000");
  });
});

describe("confirmTaskAction", () => {
  it("sends an approval and revalidates the run it belongs to", async () => {
    const confirmTask = vi.fn(async () => {});
    stub({ confirmTask });

    await expect(confirmTaskAction("task-1", true)).resolves.toEqual({ ok: true });
    expect(confirmTask).toHaveBeenCalledWith("task-1", true);
    expect(revalidatePath).toHaveBeenCalledWith("/tasks/task-1");
  });

  it("treats a rejection as an answer rather than a failure", async () => {
    const confirmTask = vi.fn(async () => {});
    stub({ confirmTask });

    await expect(confirmTaskAction("task-1", false)).resolves.toEqual({ ok: true });
    expect(confirmTask).toHaveBeenCalledWith("task-1", false);
  });

  it("reports a 409, which means the run moved on without us", async () => {
    const confirmTask = vi.fn(async () => {
      throw new ApiError(409, "the task is not awaiting confirmation");
    });
    stub({ confirmTask });

    await expect(confirmTaskAction("task-1", true)).resolves.toEqual({
      ok: false,
      message: "the task is not awaiting confirmation",
    });
  });

  it("falls back to a plain message for an error the API did not explain", async () => {
    const confirmTask = vi.fn(async () => {
      throw new TypeError("boom");
    });
    stub({ confirmTask });

    await expect(confirmTaskAction("task-1", true)).resolves.toEqual({
      ok: false,
      message: "the request failed for a reason the API did not explain",
    });
  });
});

describe("provideInputAction", () => {
  it("sends the answer the operator typed", async () => {
    const provideInput = vi.fn(async () => {});
    stub({ provideInput });

    await expect(
      provideInputAction("task-1", undefined, formData({ answer: "蓝色" })),
    ).resolves.toEqual({ ok: true });
    expect(provideInput).toHaveBeenCalledWith("task-1", "蓝色");
    expect(revalidatePath).toHaveBeenCalledWith("/tasks/task-1");
  });

  it("sends an empty answer rather than validating it here", async () => {
    const provideInput = vi.fn(async () => {});
    stub({ provideInput });

    await expect(
      provideInputAction("task-1", undefined, formData({ answer: "" })),
    ).resolves.toEqual({ ok: true });
    expect(provideInput).toHaveBeenCalledWith("task-1", "");
  });

  it("reports a 409, which means the question was already answered", async () => {
    const provideInput = vi.fn(async () => {
      throw new ApiError(409, "the task is not awaiting user input");
    });
    stub({ provideInput });

    await expect(
      provideInputAction("task-1", undefined, formData({ answer: "蓝色" })),
    ).resolves.toEqual({ ok: false, message: "the task is not awaiting user input" });
  });
});
