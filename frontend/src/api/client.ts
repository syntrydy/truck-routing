import { ApiError, parseErrorResponse } from "./errors";
import type { GeocodeResponse, Health, PlanRequest, PlanResponse, Ready } from "./types";

/** How long each kind of call may take before it is given up, in milliseconds. */
export interface Timeouts {
  /** The first call can wake a sleeping free-tier server, which takes up to a minute. */
  health: number;
  ready: number;
  geocode: number;
  /** The server's own budget for a plan is 20 s. */
  plan: number;
}

export const DEFAULT_TIMEOUTS: Timeouts = {
  health: 60_000,
  ready: 10_000,
  geocode: 8_000,
  plan: 30_000,
};

export interface ApiClientOptions {
  /** Origin of the API, without a trailing slash. Empty for the same origin. */
  baseUrl?: string;
  fetch?: typeof fetch;
  timeouts?: Partial<Timeouts>;
}

export interface ApiClient {
  health: (signal?: AbortSignal) => Promise<Health>;
  ready: (signal?: AbortSignal) => Promise<Ready>;
  geocode: (query: string, signal?: AbortSignal) => Promise<GeocodeResponse>;
  plan: (request: PlanRequest, signal?: AbortSignal) => Promise<PlanResponse>;
  /** The recorded storm: only the load and the checkpoint spacing of `request` are used. */
  demo: (request: DemoRequest, signal?: AbortSignal) => Promise<PlanResponse>;
}

/** What the demo takes from a trip: the trip itself is recorded. */
export type DemoRequest = Pick<PlanRequest, "load_lb" | "interval_mi">;

interface Call {
  path: string;
  timeoutMs: number;
  signal: AbortSignal | undefined;
  init?: RequestInit;
}

/** Makes a client for the API. `fetch` is injectable so tests need no network. */
export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const baseUrl = options.baseUrl ?? "";
  const timeouts = { ...DEFAULT_TIMEOUTS, ...options.timeouts };
  const fetchImpl = options.fetch ?? ((input, init) => fetch(input, init));

  async function request<T>(call: Call): Promise<T> {
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, call.timeoutMs);
    const abortWithCaller = () => {
      controller.abort(call.signal?.reason);
    };
    call.signal?.addEventListener("abort", abortWithCaller, { once: true });

    try {
      call.signal?.throwIfAborted(); // cancelled before it started: send nothing
      const response = await fetchImpl(`${baseUrl}${call.path}`, {
        ...call.init,
        signal: controller.signal,
      });
      if (!response.ok) {
        throw await parseErrorResponse(response);
      }
      return (await response.json()) as T;
    } catch (cause) {
      throw translate(cause, timedOut, call);
    } finally {
      clearTimeout(timer);
      call.signal?.removeEventListener("abort", abortWithCaller);
    }
  }

  return {
    health: (signal) =>
      request<Health>({ path: "/api/health", timeoutMs: timeouts.health, signal }),
    ready: (signal) => request<Ready>({ path: "/api/ready", timeoutMs: timeouts.ready, signal }),
    geocode: (query, signal) =>
      request<GeocodeResponse>({
        path: `/api/geocode?${new URLSearchParams({ q: query }).toString()}`,
        timeoutMs: timeouts.geocode,
        signal,
      }),
    demo: ({ load_lb, interval_mi }, signal) =>
      request<PlanResponse>({
        path: `/api/demo?${new URLSearchParams({
          load_lb: String(load_lb),
          interval_mi: String(interval_mi),
        }).toString()}`,
        timeoutMs: timeouts.plan,
        signal,
      }),
    plan: (body, signal) =>
      request<PlanResponse>({
        path: "/api/plan",
        timeoutMs: timeouts.plan,
        signal,
        init: {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      }),
  };
}

/** The error to throw for a failed call; a cancellation by the caller passes through as is. */
function translate(cause: unknown, timedOut: boolean, call: Call): unknown {
  if (cause instanceof ApiError) {
    return cause;
  }
  if (timedOut) {
    return new ApiError({
      code: "TIMEOUT",
      message: `The server did not answer within ${String(call.timeoutMs / 1000)} seconds`,
      status: 0,
      cause,
    });
  }
  if (call.signal?.aborted === true) {
    return cause;
  }
  if (cause instanceof SyntaxError) {
    return new ApiError({
      code: "INVALID_RESPONSE",
      message: "The server sent a response that is not valid JSON",
      status: 200,
      cause,
    });
  }
  return new ApiError({
    code: "NETWORK",
    message: "The server could not be reached",
    status: 0,
    cause,
  });
}
