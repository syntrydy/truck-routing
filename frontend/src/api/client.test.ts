import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createApiClient, DEFAULT_TIMEOUTS } from "./client.ts";
import { ApiError } from "./errors.ts";
import { errorEnvelope, jsonResponse } from "./testing.tsx";
import type { PlanRequest } from "./types.ts";

const PLAN: PlanRequest = {
  origin: { lat: 41.8781, lon: -87.6298, label: "Chicago, IL" },
  destination: { lat: 39.7392, lon: -104.9903, label: "Denver, CO" },
  departure_at: "2026-10-18T06:00:00-05:00",
  load_lb: 42000,
  interval_mi: 25,
};

type FetchMock = ReturnType<typeof vi.fn<typeof fetch>>;

function clientWith(fetchMock: FetchMock, baseUrl = "https://api.example.test") {
  return createApiClient({ baseUrl, fetch: fetchMock });
}

/** A fetch that never answers but rejects when it is aborted, like the real one. */
function hangingFetch(): FetchMock {
  return vi.fn<typeof fetch>(
    (_input, init) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("aborted", "AbortError"));
        });
      }),
  );
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("requests", () => {
  it("asks for the health of the server", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse({ status: "ok" })));

    await expect(clientWith(fetchMock).health()).resolves.toEqual({ status: "ok" });

    expect(fetchMock.mock.calls[0]?.[0]).toBe("https://api.example.test/api/health");
  });

  it("uses the same origin when no base URL is given", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse({})));

    await createApiClient({ fetch: fetchMock }).ready();

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/ready");
  });

  it("encodes the geocode query", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse({ results: [] })));

    await clientWith(fetchMock).geocode("St. Louis & co/#1");

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "https://api.example.test/api/geocode?q=St.+Louis+%26+co%2F%231",
    );
  });

  it("posts the plan request as JSON", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse({ routes: [] })));

    await clientWith(fetchMock).plan(PLAN);

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("https://api.example.test/api/plan");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(init?.body as string)).toEqual(PLAN);
  });

  it("does not send credentials or custom headers on a read", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse({ status: "ok" })));

    await clientWith(fetchMock).health();

    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.headers).toBeUndefined();
    expect(init?.credentials).toBeUndefined();
  });
});

describe("failures", () => {
  it("raises the API's error with its request ID", async () => {
    const fetchMock = vi.fn<typeof fetch>(() =>
      Promise.resolve(
        jsonResponse(errorEnvelope("NO_ROUTE", "No drivable route"), { status: 422 }),
      ),
    );

    const error = await clientWith(fetchMock)
      .plan(PLAN)
      .catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "NO_ROUTE", status: 422, requestId: "req-1" });
  });

  it("reports an unreachable server as NETWORK", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.reject(new TypeError("Failed to fetch")));

    const error = await clientWith(fetchMock)
      .health()
      .catch((e: unknown) => e);

    expect(error).toMatchObject({ code: "NETWORK", status: 0 });
    expect((error as ApiError).cause).toBeInstanceOf(TypeError);
  });

  it("reports a success response that is not JSON as INVALID_RESPONSE", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(new Response("<html></html>")));

    const error = await clientWith(fetchMock)
      .health()
      .catch((e: unknown) => e);

    expect(error).toMatchObject({ code: "INVALID_RESPONSE" });
  });
});

describe("timeouts", () => {
  it("gives up on a silent server after the timeout of the call", async () => {
    const client = clientWith(hangingFetch());
    const result = client.geocode("denver").catch((e: unknown) => e);

    await vi.advanceTimersByTimeAsync(DEFAULT_TIMEOUTS.geocode - 1);
    const early = await Promise.race([result, Promise.resolve("pending")]);
    await vi.advanceTimersByTimeAsync(1);

    expect(early).toBe("pending");
    const error = await result;
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "TIMEOUT", status: 0 });
    expect((error as ApiError).message).toContain("8 seconds");
  });

  it.each([
    ["health", 60_000, (c: ReturnType<typeof clientWith>) => c.health()],
    ["ready", 10_000, (c: ReturnType<typeof clientWith>) => c.ready()],
    ["plan", 30_000, (c: ReturnType<typeof clientWith>) => c.plan(PLAN)],
  ])("%s waits %d ms", async (_name, ms, call) => {
    const result = call(clientWith(hangingFetch())).catch((e: unknown) => e);

    await vi.advanceTimersByTimeAsync(ms);

    expect(await result).toMatchObject({ code: "TIMEOUT" });
  });

  it("takes the timeouts from the options", async () => {
    const client = createApiClient({ fetch: hangingFetch(), timeouts: { health: 100 } });
    const result = client.health().catch((e: unknown) => e);

    await vi.advanceTimersByTimeAsync(100);

    expect(await result).toMatchObject({ code: "TIMEOUT" });
  });

  it("stops the clock once the answer is in", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse({ status: "ok" })));
    await clientWith(fetchMock).health();

    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("cancellation", () => {
  it("passes the caller's cancellation through as it is, not as an API error", async () => {
    const controller = new AbortController();
    const result = clientWith(hangingFetch())
      .plan(PLAN, controller.signal)
      .catch((e: unknown) => e);

    controller.abort();

    const error = await result;
    expect(error).not.toBeInstanceOf(ApiError);
    expect(controller.signal.aborted).toBe(true);
  });

  it("never sends a request that was cancelled before it started", async () => {
    const fetchMock = hangingFetch();
    const controller = new AbortController();
    controller.abort();

    const error = await clientWith(fetchMock)
      .health(controller.signal)
      .catch((e: unknown) => e);

    expect(error).not.toBeInstanceOf(ApiError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("clears its timer after a cancellation", async () => {
    const controller = new AbortController();
    const result = clientWith(hangingFetch())
      .health(controller.signal)
      .catch((e: unknown) => e);
    controller.abort();
    await result;

    expect(vi.getTimerCount()).toBe(0);
  });
});
