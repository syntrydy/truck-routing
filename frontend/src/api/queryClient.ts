import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./errors";

const MAX_RETRIES = 2;
const HTTP_CLIENT_ERROR = 400;
const HTTP_SERVER_ERROR = 500;

/**
 * Whether to try a failed query again. A request the server refused (a 4xx) will be refused
 * again, so only outages, timeouts and network failures are retried.
 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= MAX_RETRIES) {
    return false;
  }
  if (!(error instanceof ApiError)) {
    return false;
  }
  const refused = error.status >= HTTP_CLIENT_ERROR && error.status < HTTP_SERVER_ERROR;
  return !refused;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetry, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}
