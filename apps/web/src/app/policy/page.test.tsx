import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import PolicyPage from "./page";
import { ApiUnavailableError } from "@/lib/api";
import type { PolicyView } from "@/lib/types";
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

function policy(overrides: Partial<PolicyView> = {}): PolicyView {
  return {
    thresholds: {
      confirmation: 0.75,
      risk: 2.5,
      reasoning: 0.7,
      confidence: 0.75,
      completion: 0.75,
    },
    tools: [
      {
        name: "calculator",
        risk: "read",
        description: "计算表达式",
        requires_confirmation: false,
      },
      {
        name: "send_mock_email",
        risk: "external",
        description: "发送一封模拟邮件",
        requires_confirmation: true,
      },
    ],
    confirmation_ttl_seconds: 900,
    confirmation_binding: "task + action + arguments",
    ...overrides,
  };
}

describe("policy page", () => {
  it("shows the thresholds that are actually in force", async () => {
    createApiClient.mockReturnValue(apiClientStub({ getPolicy: async () => policy() }));

    const html = renderPage(await PolicyPage());

    expect(html).toContain("确认概率阈值");
    expect(html).toContain("0.75");
    expect(html).toContain("2.5");
    expect(html).toContain("完成度阈值");
  });

  it("marks which tools must be confirmed and why", async () => {
    createApiClient.mockReturnValue(apiClientStub({ getPolicy: async () => policy() }));

    const html = renderPage(await PolicyPage());

    expect(html).toContain("send_mock_email");
    expect(html).toContain("外部副作用");
    expect(html).toContain("calculator");
    expect(html).toContain("读取");
  });

  it("tells the reader how to recalibrate instead of trusting the defaults", async () => {
    createApiClient.mockReturnValue(apiClientStub({ getPolicy: async () => policy() }));

    const html = renderPage(await PolicyPage());

    expect(html).toContain("--mode calibrate");
    expect(html).toContain("15 分钟");
  });

  it("reports an unreachable API as a configuration problem", async () => {
    createApiClient.mockReturnValue(
      apiClientStub({
        getPolicy: async () => {
          throw new ApiUnavailableError("http://127.0.0.1:8000", "connect ECONNREFUSED");
        },
      }),
    );

    const html = renderPage(await PolicyPage());

    expect(html).toContain("无法读取当前策略");
    expect(html).toContain("http://127.0.0.1:8000");
  });
});
