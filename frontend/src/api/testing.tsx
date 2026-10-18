import { QueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { ApiProvider } from "./ApiProvider.tsx";
import type { ApiClient } from "./client.ts";

/** A response with a JSON body, as the API sends them. */
export function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  return new Response(JSON.stringify(body), { ...init, headers });
}

export function errorEnvelope(code: string, message = "Something", field: string | null = null) {
  return { error: { code, message, field, request_id: "req-1" } };
}

/** An API client whose every method is a mock, for components that call the API. */
export function stubClient(overrides: Partial<ApiClient> = {}): ApiClient {
  const unexpected = () => Promise.reject(new Error("unexpected API call"));
  return {
    health: unexpected,
    ready: unexpected,
    geocode: unexpected,
    plan: unexpected,
    demo: unexpected,
    ...overrides,
  };
}

/** A wrapper that provides `client` and a query cache that never retries or caches. */
export function apiWrapper(client: ApiClient) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <ApiProvider client={client} queryClient={queryClient}>
        {children}
      </ApiProvider>
    );
  };
}
