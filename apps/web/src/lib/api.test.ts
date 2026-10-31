import { describe, expect, it, vi } from "vitest";

import {
  ApiError,
  ApiUnavailableError,
  DEFAULT_UPSTREAM,
  createApiClient,
  describeProblem,
  readFromApi,
  resolveUpstream,
  type FetchLike,
} from "./api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubFetch(handler: (input: string, init?: RequestInit) => Response | Promise<Response>) {
  const calls: Array<{ input: string; init?: RequestInit }> = [];
  const fetchImpl: FetchLike = vi.fn(async (input, init) => {
    calls.push({ input, init });
    return handler(input, init);
  });
  return { calls, fetchImpl };
}

const UPSTREAM = "http://api.test:8000";

describe("resolveUpstream", () => {
  it("falls back to the documented default", () => {
    expect(resolveUpstream({})).toBe(DEFAULT_UPSTREAM);
    expect(resolveUpstream({ API_UPSTREAM_URL: "   " })).toBe(DEFAULT_UPSTREAM);
  });

  it("trims and drops a trailing slash so paths join cleanly", () => {
    expect(resolveUpstream({ API_UPSTREAM_URL: " http://api.test:8000/ " })).toBe("http://api.test:8000");
  });
});

describe("describeProblem", () => {
  it("reads an HTTPException detail string", () => {
    expect(describeProblem({ detail: "task not found" })).toBe("task not found");
  });

  it("flattens a validation error list into one line", () => {
    const flattened = describeProblem({
      detail: [
        { loc: ["body", "goal"], msg: "String should have at least 1 character" },
        { loc: ["body"], msg: "Extra inputs are not permitted" },
      ],
    });
    expect(flattened).toBe(
      "body.goal: String should have at least 1 character; body: Extra inputs are not permitted",
    );
  });

  it("returns nothing to say when the body carries nothing", () => {
    expect(describeProblem({})).toBe("");
    expect(describeProblem(null)).toBe("");
    expect(describeProblem("nope")).toBe("nope");
  });
});

describe("createApiClient", () => {
  it("lists tasks with an optional limit", async () => {
    const { calls, fetchImpl } = stubFetch(() => jsonResponse({ tasks: [] }));
    const client = createApiClient({ upstream: UPSTREAM, fetchImpl });

    await client.listTasks();
    await client.listTasks(5);

    expect(calls[0].input).toBe(`${UPSTREAM}/tasks`);
    expect(calls[1].input).toBe(`${UPSTREAM}/tasks?limit=5`);
    expect(calls[1].init?.method).toBeUndefined();
  });

  it("reads one task and its traces", async () => {
    const { calls, fetchImpl } = stubFetch(() =>
      jsonResponse({ task_id: "abc", traces: [] }),
    );
    const client = createApiClient({ upstream: UPSTREAM, fetchImpl });

    await client.getTask("abc");
    await client.getTraces("abc");

    expect(calls[0].input).toBe(`${UPSTREAM}/tasks/abc`);
    expect(calls[1].input).toBe(`${UPSTREAM}/tasks/abc/traces`);
  });

  it("submits a goal and omits an absent context", async () => {
    const { calls, fetchImpl } = stubFetch(() => jsonResponse({ task_id: "abc", status: "running" }, 202));
    const client = createApiClient({ upstream: UPSTREAM, fetchImpl });

    await client.submitTask("Calculate 2 + 2");
    await client.submitTask("Summarize", { topic: "routing" });

    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ goal: "Calculate 2 + 2" });
    expect(JSON.parse(String(calls[1].init?.body))).toEqual({
      goal: "Summarize",
      context: { topic: "routing" },
    });
  });

  it("sends a confirmation and an answer as JSON", async () => {
    const { calls, fetchImpl } = stubFetch(() => new Response(null, { status: 204 }));
    const client = createApiClient({ upstream: UPSTREAM, fetchImpl });

    await client.confirmTask("abc", true, "digest-1");
    await client.provideInput("abc", "42");

    expect(calls[0].input).toBe(`${UPSTREAM}/tasks/abc/confirm`);
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({
      approved: true,
      digest: "digest-1",
    });
    expect(calls[1].input).toBe(`${UPSTREAM}/tasks/abc/input`);
    expect(JSON.parse(String(calls[1].init?.body))).toEqual({ answer: "42" });
  });

  it("maps a 404 to an ApiError carrying the API's message", async () => {
    const { fetchImpl } = stubFetch(() => jsonResponse({ detail: "task not found" }, 404));
    const client = createApiClient({ upstream: UPSTREAM, fetchImpl });

    await expect(client.getTask("missing")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      message: "task not found",
    });
  });

  it("maps a 409 to an ApiError so a stale answer can be reported", async () => {
    const { fetchImpl } = stubFetch(() =>
      jsonResponse({ detail: "the task is not awaiting confirmation" }, 409),
    );
    const client = createApiClient({ upstream: UPSTREAM, fetchImpl });

    const error = await client.confirmTask("abc", true, "digest-1").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(409);
  });

  it("maps a connection failure to an unavailable upstream, naming it", async () => {
    const fetchImpl: FetchLike = vi.fn(async () => {
      throw new Error("connect ECONNREFUSED");
    });
    const client = createApiClient({ upstream: UPSTREAM, fetchImpl });

    const error = await client.listTasks().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiUnavailableError);
    expect((error as ApiUnavailableError).upstream).toBe(UPSTREAM);
    expect((error as Error).message).toContain("connect ECONNREFUSED");
  });

  it("reports a success body that is not JSON instead of crashing the page", async () => {
    const { fetchImpl } = stubFetch(() => new Response("<html>", { status: 200 }));
    const client = createApiClient({ upstream: UPSTREAM, fetchImpl });

    await expect(client.getTask("abc")).rejects.toBeInstanceOf(ApiError);
  });

  it("encodes a task id so a path-like id cannot escape its route", async () => {
    const { calls, fetchImpl } = stubFetch(() => jsonResponse({ tasks: [] }));
    const client = createApiClient({ upstream: UPSTREAM, fetchImpl });

    await client.getTask("../../admin");

    expect(calls[0].input).toBe(`${UPSTREAM}/tasks/..%2F..%2Fadmin`);
  });
});

describe("readFromApi", () => {
  it("passes a successful read through", async () => {
    const result = await readFromApi(async () => "value");
    expect(result).toEqual({ ok: true, value: "value" });
  });

  it("marks an unreachable upstream as unavailable, which is a configuration problem", async () => {
    const result = await readFromApi(async () => {
      throw new ApiUnavailableError(UPSTREAM, "connect ECONNREFUSED");
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.unavailable).toBe(true);
      expect(result.message).toContain(UPSTREAM);
    }
  });

  it("marks an answered error as available, which is a fact about the run", async () => {
    const result = await readFromApi(async () => {
      throw new ApiError(404, "task not found");
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.unavailable).toBe(false);
      expect(result.message).toBe("task not found");
    }
  });

  it("does not let an unexpected error escape as a crash", async () => {
    const result = await readFromApi(async () => {
      throw new TypeError("boom");
    });
    expect(result).toEqual({
      ok: false,
      message: "the API could not be read",
      unavailable: false,
    });
  });
});

describe("eval reads", () => {
  const summary = {
    run_id: "run-1",
    mode: "compare",
    created_at: "2026-09-24T00:00:00+00:00",
    case_count: 50,
  };

  it("lists eval runs with an optional limit", async () => {
    const { calls, fetchImpl } = stubFetch(() => jsonResponse({ runs: [summary] }));
    const client = createApiClient({ upstream: UPSTREAM, fetchImpl });

    const listed = await client.listEvalRuns(5);

    expect(calls[0].input).toBe(`${UPSTREAM}/evals?limit=5`);
    expect(listed.runs).toEqual([summary]);
  });

  it("reads one eval run and encodes its id", async () => {
    const { calls, fetchImpl } = stubFetch(() =>
      jsonResponse({ ...summary, metrics: {}, outcomes: [] }),
    );
    const client = createApiClient({ upstream: UPSTREAM, fetchImpl });

    await client.getEvalRun("../../runs");

    expect(calls[0].input).toBe(`${UPSTREAM}/evals/..%2F..%2Fruns`);
  });

  it("maps a 404 on an unknown run to an ApiError", async () => {
    const { fetchImpl } = stubFetch(() => jsonResponse({ detail: "eval run not found" }, 404));
    const client = createApiClient({ upstream: UPSTREAM, fetchImpl });

    await expect(client.getEvalRun("missing")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      message: "eval run not found",
    });
  });
});
