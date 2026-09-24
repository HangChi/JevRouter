import type {
  EvalRunListResponse,
  EvalRunView,
  SubmitTaskResponse,
  TaskListResponse,
  TaskView,
  TraceListResponse,
} from "./types";

/**
 * Server-only client for the JevRouter API.
 *
 * Every call happens on the server — in server components for reads and in
 * server actions for writes — so the browser never talks to `apps/api` and no
 * credential is configured here. The one piece of configuration is where the
 * API lives.
 */

export const DEFAULT_UPSTREAM = "http://127.0.0.1:8000";

/** The API answered, but not with a success. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** The API could not be reached at all, which is a different problem. */
export class ApiUnavailableError extends Error {
  readonly upstream: string;

  constructor(upstream: string, reason: string) {
    super(`the API at ${upstream} could not be reached: ${reason}`);
    this.name = "ApiUnavailableError";
    this.upstream = upstream;
  }
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

/**
 * The outcome of one read, with the two failure kinds kept apart: an unreachable
 * upstream is a misconfigured dashboard, while an error the API answered is a
 * fact about the run. They are reported differently.
 */
export type ReadResult<T> =
  | { ok: true; value: T }
  | { ok: false; message: string; unavailable: boolean };

export async function readFromApi<T>(load: () => Promise<T>): Promise<ReadResult<T>> {
  try {
    return { ok: true, value: await load() };
  } catch (error) {
    if (error instanceof ApiUnavailableError) {
      return { ok: false, message: error.message, unavailable: true };
    }
    if (error instanceof ApiError) {
      return { ok: false, message: error.message, unavailable: false };
    }
    return { ok: false, message: "the API could not be read", unavailable: false };
  }
}

export interface ApiClient {
  listTasks(limit?: number): Promise<TaskListResponse>;
  getTask(taskId: string): Promise<TaskView>;
  getTraces(taskId: string): Promise<TraceListResponse>;
  submitTask(goal: string, context?: Record<string, unknown>): Promise<SubmitTaskResponse>;
  confirmTask(taskId: string, approved: boolean): Promise<void>;
  provideInput(taskId: string, answer: string): Promise<void>;
  listEvalRuns(limit?: number): Promise<EvalRunListResponse>;
  getEvalRun(runId: string): Promise<EvalRunView>;
}

export interface ApiClientOptions {
  upstream?: string;
  fetchImpl?: FetchLike;
  /** A hung upstream must not hang a server render, so requests are bounded. */
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 10_000;

/**
 * Resolve the upstream from the environment, tolerating a missing variable and
 * a trailing slash so `API_UPSTREAM_URL=http://api:8000/` still joins cleanly.
 */
export function resolveUpstream(env: Record<string, string | undefined>): string {
  const raw = env.API_UPSTREAM_URL;
  if (raw === undefined || raw.trim() === "") {
    return DEFAULT_UPSTREAM;
  }
  return raw.trim().replace(/\/+$/, "");
}

/**
 * Turn a FastAPI error body into one line. `HTTPException` carries a string
 * `detail`; request validation carries a list of `{ loc, msg }` entries.
 */
export function describeProblem(body: unknown): string {
  if (typeof body === "string" && body.trim() !== "") {
    return body.trim();
  }
  if (typeof body !== "object" || body === null) {
    return "";
  }
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim() !== "") {
    return detail.trim();
  }
  if (Array.isArray(detail)) {
    const lines = detail.map((entry) => {
      if (typeof entry !== "object" || entry === null) {
        return JSON.stringify(entry);
      }
      const { loc, msg } = entry as { loc?: unknown; msg?: unknown };
      const where = Array.isArray(loc)
        ? loc.filter((part) => typeof part === "string" || typeof part === "number").join(".")
        : "";
      const text = typeof msg === "string" ? msg : JSON.stringify(entry);
      return where === "" ? text : `${where}: ${text}`;
    });
    return lines.join("; ");
  }
  return "";
}

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const upstream = options.upstream ?? resolveUpstream(process.env);
  const fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetchImpl(`${upstream}${path}`, {
        ...init,
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (error) {
      throw new ApiUnavailableError(upstream, error instanceof Error ? error.message : String(error));
    }
    if (!response.ok) {
      const problem = await readProblem(response);
      throw new ApiError(response.status, problem || `the API answered ${response.status}`);
    }
    if (response.status === 204) {
      return undefined as T;
    }
    try {
      return (await response.json()) as T;
    } catch (error) {
      throw new ApiError(
        response.status,
        `the API answered ${response.status} with a body that is not JSON: ${
          error instanceof Error ? error.message : String(error)
        }`,
      );
    }
  }

  async function readProblem(response: Response): Promise<string> {
    try {
      return describeProblem(await response.json());
    } catch {
      return "";
    }
  }

  return {
    async listTasks(limit?: number) {
      const query = limit === undefined ? "" : `?limit=${encodeURIComponent(String(limit))}`;
      return request<TaskListResponse>(`/tasks${query}`);
    },

    async getTask(taskId) {
      return request<TaskView>(`/tasks/${encodeURIComponent(taskId)}`);
    },

    async getTraces(taskId) {
      return request<TraceListResponse>(`/tasks/${encodeURIComponent(taskId)}/traces`);
    },

    async submitTask(goal, context) {
      const body: Record<string, unknown> = { goal };
      if (context !== undefined) {
        body.context = context;
      }
      return request<SubmitTaskResponse>("/tasks", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
    },

    async confirmTask(taskId, approved) {
      await request<void>(`/tasks/${encodeURIComponent(taskId)}/confirm`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ approved }),
      });
    },

    async provideInput(taskId, answer) {
      await request<void>(`/tasks/${encodeURIComponent(taskId)}/input`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ answer }),
      });
    },

    async listEvalRuns(limit) {
      const query = limit === undefined ? "" : `?limit=${encodeURIComponent(String(limit))}`;
      return request<EvalRunListResponse>(`/evals${query}`);
    },

    async getEvalRun(runId) {
      return request<EvalRunView>(`/evals/${encodeURIComponent(runId)}`);
    },
  };
}
