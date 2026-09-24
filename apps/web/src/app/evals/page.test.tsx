import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import EvalsPage from "./page";
import { ApiError, ApiUnavailableError } from "@/lib/api";
import type { EvalComparisonMetrics, EvalModeMetrics, EvalRunSummary, EvalRunView } from "@/lib/types";
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

function metrics(mode: "jev" | "llm", overrides: Partial<EvalModeMetrics> = {}): EvalModeMetrics {
  const baseline = mode === "llm";
  return {
    mode,
    case_count: 50,
    error_count: 0,
    expected_match_count: 44,
    allowed_match_count: 47,
    success_count: 41,
    escalation_count: baseline ? null : 4,
    confirmation_expected_count: baseline ? null : 17,
    confirmation_requested_count: baseline ? null : 15,
    confirmation_match_count: baseline ? null : 45,
    expected_match_rate: 0.88,
    allowed_match_rate: 0.94,
    success_rate: 0.82,
    error_rate: 0,
    escalation_rate: baseline ? null : 0.08,
    latency: { mean_ms: 118.4, p50_ms: 104, p95_ms: 210, max_ms: 402 },
    input_tokens: { mean: 423.2, total: 21160 },
    output_tokens: { mean: 12.1, total: 605 },
    ...overrides,
  };
}

function comparison(overrides: Partial<EvalComparisonMetrics> = {}): EvalComparisonMetrics {
  return {
    jev: metrics("jev"),
    llm: metrics("llm"),
    agreement_count: 46,
    compared_count: 50,
    agreement_rate: 0.92,
    disagreement_case_ids: ["case-3", "case-17"],
    ...overrides,
  };
}

function run(overrides: Partial<EvalRunSummary> = {}): EvalRunSummary {
  return {
    run_id: "82085550761c48a990e81570d6576fa7",
    mode: "compare",
    created_at: "2026-09-24T08:05:42.855837+00:00",
    case_count: 50,
    ...overrides,
  };
}

function runView(overrides: Partial<EvalRunView> = {}): EvalRunView {
  const summary = run();
  return {
    ...summary,
    metrics: comparison(),
    outcomes: [],
    ...overrides,
  };
}

function stubReads(runs: EvalRunSummary[], detail?: EvalRunView | Error): void {
  createApiClient.mockReturnValue(
    apiClientStub({
      listEvalRuns: async () => ({ runs }),
      getEvalRun: async (runId: string) => {
        if (detail instanceof Error) {
          throw detail;
        }
        return detail ?? runView({ run_id: runId });
      },
    }),
  );
}

describe("evals page", () => {
  it("shows the newest run's metrics beside the runs it keeps", async () => {
    stubReads([run()], runView());

    const html = renderPage(await EvalsPage());

    expect(html).toContain("最新一次 · compare · 50 个用例");
    expect(html).toContain("一致率");
    expect(html).toContain("92.0%");
    expect(html).toContain("46/50 个可比用例选择了相同动作");
    expect(html).toContain("已记录的运行");
    expect(html).toContain("82085550");
    expect(html).toContain("50 个用例");
  });

  it("keeps the two routers apart, labelling the baseline as the baseline", async () => {
    stubReads([run()], runView());

    const html = renderPage(await EvalsPage());

    expect(html).toContain(">Jev</h3>");
    expect(html).toContain(">LLM 基线</h3>");
  });

  it("still lists the runs when the newest one cannot be read", async () => {
    stubReads([run()], new ApiError(500, "the run could not be loaded"));

    const html = renderPage(await EvalsPage());

    expect(html).toContain("无法读取最新一次运行");
    expect(html).toContain("82085550");
    expect(html).not.toContain("一致率");
  });

  it("explains how to record a run when none has been", async () => {
    stubReads([]);

    const html = renderPage(await EvalsPage());

    expect(html).toContain("还没有记录过 eval 运行");
    expect(html).toContain("uv run python -m evals --mode compare");
    // No run means no metrics section, only the list heading and its empty state.
    expect(html).not.toContain("一致率");
  });

  it("reports an unreachable API as a configuration problem", async () => {
    createApiClient.mockReturnValue(
      apiClientStub({
        listEvalRuns: async () => {
          throw new ApiUnavailableError("http://127.0.0.1:8000", "connect ECONNREFUSED");
        },
      }),
    );

    const html = renderPage(await EvalsPage());

    expect(html).toContain("无法读取评测列表");
    expect(html).toContain("http://127.0.0.1:8000");
  });
});
