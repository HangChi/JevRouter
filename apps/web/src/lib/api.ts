import type {
  EvalRunListResponse,
  EvalRunView,
  PolicyView,
  SubmitTaskResponse,
  TaskListResponse,
  TaskView,
  TraceListResponse,
} from "./types";

/**
 * 仅服务端使用的 JevRouter API 客户端。
 *
 * 所有调用都在服务端发生——读取在服务端组件里，写入在服务端 action 里——因此
 * 浏览器从不直接访问 `apps/api`，这里也不需要配置任何凭证。唯一的配置项是
 * API 所在的位置。
 */

export const DEFAULT_UPSTREAM = "http://127.0.0.1:8000";

/** API 应答了，但不是一个成功应答。 */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** API 完全无法连接，这是另一类问题。 */
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
 * 一次读取的结果，两种失败被分开保存：上游不可达意味着仪表盘配置有误，而 API
 * 应答的错误是关于这次运行本身的事实。两者的上报方式不同。
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
  confirmTask(taskId: string, approved: boolean, digest: string): Promise<void>;
  provideInput(taskId: string, answer: string): Promise<void>;
  listEvalRuns(limit?: number): Promise<EvalRunListResponse>;
  getEvalRun(runId: string): Promise<EvalRunView>;
  getPolicy(): Promise<PolicyView>;
}

export interface ApiClientOptions {
  upstream?: string;
  fetchImpl?: FetchLike;
  /** 上游卡住不能把服务端渲染也卡住，因此请求都有超时上限。 */
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 10_000;

/**
 * 从环境变量解析上游地址，同时容忍变量缺失和结尾斜杠，让
 * `API_UPSTREAM_URL=http://api:8000/` 也能干净地拼接路径。
 */
export function resolveUpstream(env: Record<string, string | undefined>): string {
  const raw = env.API_UPSTREAM_URL;
  if (raw === undefined || raw.trim() === "") {
    return DEFAULT_UPSTREAM;
  }
  return raw.trim().replace(/\/+$/, "");
}

/**
 * 把 FastAPI 的错误体压成一行。`HTTPException` 携带字符串 `detail`；请求校验
 * 错误携带一个由 `{ loc, msg }` 条目组成的列表。
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

    async confirmTask(taskId, approved, digest) {
      await request<void>(`/tasks/${encodeURIComponent(taskId)}/confirm`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ approved, digest }),
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

    async getPolicy() {
      return request<PolicyView>("/policy");
    },
  };
}
