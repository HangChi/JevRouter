import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import TaskPage from "./page";
import { ApiError, ApiUnavailableError } from "@/lib/api";
import type { TaskView, TraceView } from "@/lib/types";
import { apiClientStub, renderPage } from "@/test/support";

const { createApiClient } = vi.hoisted(() => ({ createApiClient: vi.fn() }));

vi.mock("next/server", () => ({ connection: async () => {} }));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Error(`redirect:${to}`);
  },
  notFound: () => {
    throw new Error("notFound");
  },
  // LiveRefresh polls by refreshing the route; a static render only needs the
  // hook to exist.
  useRouter: () => ({ refresh: vi.fn() }),
}));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, createApiClient };
});

beforeEach(() => {
  vi.clearAllMocks();
});

function task(overrides: Partial<TaskView> = {}): TaskView {
  return {
    task_id: "0123456789abcdef",
    goal: "计算 6 * 7，然后把结果写进 notes.md",
    status: "completed",
    step: 1,
    diagnostic: null,
    pending_confirmation: null,
    pending_input: null,
    ...overrides,
  };
}

function trace(overrides: Partial<TraceView> = {}): TraceView {
  return {
    step: 1,
    action: "calculator",
    policy_outcome: "execute",
    policy_reason: "The registered action is permitted by the configured thresholds.",
    executed: true,
    result: { value: 42 },
    route_confidence: 0.9,
    route_risk: 1,
    requires_confirmation: 0.1,
    needs_reasoning: 0.2,
    confirmed: null,
    arguments: { expression: "6 * 7" },
    completion_probability: 0.8,
    quality_score: 3,
    state_snapshot: { goal: "计算 6 * 7" },
    duration_ms: 120,
    ...overrides,
  };
}

function params(taskId = "0123456789abcdef"): PageProps<"/tasks/[taskId]"> {
  return {
    params: Promise.resolve({ taskId }),
    searchParams: Promise.resolve({}),
  };
}

function stubTask(view: TaskView, traces: TraceView[] = [trace()]): void {
  createApiClient.mockReturnValue(
    apiClientStub({
      getTask: async () => view,
      getTraces: async () => ({ task_id: view.task_id, traces }),
    }),
  );
}

describe("task page", () => {
  it("renders the run, its recorded steps and the decision chain", async () => {
    stubTask(task());

    const html = renderPage(await TaskPage(params()));

    expect(html).toContain("计算 6 * 7，然后把结果写进 notes.md");
    expect(html).toContain("已完成");
    expect(html).toContain("已记录 1 步");
    expect(html).toContain("决策链");
    expect(html).toContain("calculator");
    expect(html).toContain("步骤");
  });

  it("shows the action and its resolved arguments when a human must decide", async () => {
    stubTask(
      task({
        status: "awaiting_confirmation",
        step: 0,
        pending_confirmation: {
          action: "send_mock_email",
          arguments: { to: "team@example.com", subject: "周报" },
          step: 0,
        },
      }),
      [],
    );

    const html = renderPage(await TaskPage(params()));

    expect(html).toContain("等待你处理");
    expect(html).toContain("send_mock_email");
    expect(html).toContain("待执行参数");
    expect(html).toContain("team@example.com");
    expect(html).toContain("批准");
    expect(html).toContain("拒绝");
  });

  it("shows the question the run is blocked on", async () => {
    stubTask(
      task({
        status: "awaiting_input",
        step: 0,
        pending_input: { question: "要写入哪个文件？", step: 0 },
      }),
      [],
    );

    const html = renderPage(await TaskPage(params()));

    expect(html).toContain("要写入哪个文件？");
    expect(html).toContain('name="answer"');
    expect(html).toContain("发送");
    expect(html).not.toContain("批准");
  });

  it("surfaces a diagnostic the run finished with", async () => {
    stubTask(task({ status: "failed", diagnostic: "the provider refused the request" }));

    const html = renderPage(await TaskPage(params()));

    expect(html).toContain("诊断信息");
    expect(html).toContain("the provider refused the request");
  });

  it("falls to the not-found page when the API answers that it does not know the run", async () => {
    createApiClient.mockReturnValue(
      apiClientStub({
        getTask: async () => {
          throw new ApiError(404, "task not found");
        },
      }),
    );

    await expect(TaskPage(params("unknown"))).rejects.toThrow("notFound");
  });

  it("reports an unreachable API rather than pretending the run is missing", async () => {
    createApiClient.mockReturnValue(
      apiClientStub({
        getTask: async () => {
          throw new ApiUnavailableError("http://127.0.0.1:8000", "connect ECONNREFUSED");
        },
      }),
    );

    const html = renderPage(await TaskPage(params()));

    expect(html).toContain("无法连接到 API");
    expect(html).toContain("http://127.0.0.1:8000");
  });

  it("still renders the run when only its traces cannot be read", async () => {
    createApiClient.mockReturnValue(
      apiClientStub({
        getTask: async () => task(),
        getTraces: async () => {
          throw new ApiError(500, "the store could not be read");
        },
      }),
    );

    const html = renderPage(await TaskPage(params()));

    expect(html).toContain("计算 6 * 7，然后把结果写进 notes.md");
    expect(html).toContain("无法读取 trace");
    expect(html).toContain("还没有已完成的步骤。");
  });
});
