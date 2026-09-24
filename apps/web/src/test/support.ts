import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { ApiClient } from "@/lib/api";

/**
 * Render a page so a test can assert on its markup.
 *
 * A server component is an async function, so a test awaits it first and hands
 * the resulting element to a static render — no DOM and no RSC runtime needed.
 * React separates adjacent text nodes with a comment; dropping it lets the
 * assertions read as the text an operator sees.
 */
export function renderPage(element: ReactElement): string {
  return renderToStaticMarkup(element).replace(/<!-- -->/g, "");
}

/**
 * An API client whose unstubbed methods fail loudly.
 *
 * A method a test forgot to stub returning `undefined` would let the page render
 * an empty state and the test pass on the wrong branch.
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
    ...overrides,
  };
}
