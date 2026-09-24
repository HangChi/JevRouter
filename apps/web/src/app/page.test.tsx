import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import Home from "./page";
import { ApiUnavailableError } from "@/lib/api";
import type { TaskSummary } from "@/lib/types";
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

function summary(overrides: Partial<TaskSummary> = {}): TaskSummary {
  return {
    task_id: "0123456789abcdef",
    goal: "计算 6 * 7，然后把结果写进 notes.md",
    status: "completed",
    step: 2,
    ...overrides,
  };
}

function stubTasks(tasks: TaskSummary[]): void {
  createApiClient.mockReturnValue(apiClientStub({ listTasks: async () => ({ tasks }) }));
}

describe("home page", () => {
  it("renders the runs the API returned, newest first", async () => {
    stubTasks([
      summary(),
      summary({
        task_id: "fedcba9876543210",
        goal: "给团队发一封摘要邮件",
        status: "failed",
        step: 0,
      }),
    ]);

    const html = renderPage(await Home());

    expect(html).toContain('href="/tasks/0123456789abcdef"');
    expect(html).toContain("计算 6 * 7，然后把结果写进 notes.md");
    expect(html).toContain("01234567");
    expect(html).toContain("已完成");
    expect(html).toContain("2 步");
    expect(html).toContain("给团队发一封摘要邮件");
    expect(html).toContain("失败");
    expect(html).toContain('href="/tasks/fedcba9876543210"');
  });

  it("shows no step count for a run that has not finished one", async () => {
    stubTasks([summary({ status: "running", step: 0 })]);

    const html = renderPage(await Home());

    expect(html).toContain("运行中");
    expect(html).not.toContain("0 步");
  });

  it("explains an empty list instead of rendering an empty table", async () => {
    stubTasks([]);

    const html = renderPage(await Home());

    expect(html).toContain("还没有运行。在上方提交一个目标即可开始。");
    expect(html).not.toContain("<ul");
  });

  it("reports an unreachable API as a configuration problem, not an empty system", async () => {
    createApiClient.mockReturnValue(
      apiClientStub({
        listTasks: async () => {
          throw new ApiUnavailableError("http://127.0.0.1:8000", "connect ECONNREFUSED");
        },
      }),
    );

    const html = renderPage(await Home());

    expect(html).toContain("无法读取运行列表");
    expect(html).toContain("http://127.0.0.1:8000");
    expect(html).not.toContain("还没有运行");
  });

  it("offers the submit form whatever the API says", async () => {
    stubTasks([]);

    const html = renderPage(await Home());

    expect(html).toContain('name="goal"');
    expect(html).toContain('name="context"');
    expect(html).toContain("开始运行");
  });
});
