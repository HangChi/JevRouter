import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { ApiClient } from "@/lib/api";

/**
 * 静态渲染一个页面，好让测试断言它的标记。
 *
 * 服务端组件是异步函数，所以测试先 await 它，再把得到的元素交给静态渲染——
 * 既不需要 DOM，也不需要 RSC 运行时。React 会在相邻文本节点之间插入注释，
 * 去掉它，断言读起来就是运维者看到的文本。
 */
export function renderPage(element: ReactElement): string {
  return renderToStaticMarkup(element).replace(/<!-- -->/g, "");
}

/**
 * 一个未打桩的方法会大声报错的 API 客户端。
 *
 * 测试忘了打桩的方法如果返回 `undefined`，页面就会渲染成空状态，测试也就
 * 会在错误的分支上通过。
 */
export function apiClientStub(overrides: Partial<ApiClient>): ApiClient {
  const missing = (name: string) => async (): Promise<never> => {
    throw new Error(`${name} was not stubbed for this test`);
  };
  return {
    listTasks: missing("listTasks"),
    getTask: missing("getTask"),
    getTraces: missing("getTraces"),
    submitTask: missing("submitTask"),
    confirmTask: missing("confirmTask"),
    provideInput: missing("provideInput"),
    listEvalRuns: missing("listEvalRuns"),
    getEvalRun: missing("getEvalRun"),
    getPolicy: missing("getPolicy"),
    ...overrides,
  };
}
