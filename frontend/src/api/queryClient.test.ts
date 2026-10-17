import { describe, expect, it } from "vitest";

import { ApiError, type ApiErrorCode } from "./errors.ts";
import { createQueryClient, shouldRetry } from "./queryClient.ts";

function failure(code: ApiErrorCode, status: number): ApiError {
  return new ApiError({ code, message: "failed", status });
}

describe("shouldRetry", () => {
  it.each([
    ["a refused request", failure("VALIDATION", 400)],
    ["a missing route", failure("NO_ROUTE", 422)],
    ["a rate limit", failure("RATE_LIMITED", 429)],
    ["a missing page", failure("NOT_FOUND", 404)],
  ])("does not retry %s", (_name, error) => {
    expect(shouldRetry(0, error)).toBe(false);
  });

  it.each([
    ["an outage", failure("UPSTREAM_UNAVAILABLE", 503)],
    ["a bad gateway", failure("UPSTREAM_ERROR", 502)],
    ["a server timeout", failure("UPSTREAM_TIMEOUT", 504)],
    ["a client timeout", failure("TIMEOUT", 0)],
    ["no network", failure("NETWORK", 0)],
  ])("retries %s", (_name, error) => {
    expect(shouldRetry(0, error)).toBe(true);
    expect(shouldRetry(1, error)).toBe(true);
  });

  it("gives up after two retries", () => {
    expect(shouldRetry(2, failure("NETWORK", 0))).toBe(false);
  });

  it("does not retry a failure it does not understand", () => {
    expect(shouldRetry(0, new Error("bug"))).toBe(false);
  });
});

describe("createQueryClient", () => {
  it("retries queries by that rule and never retries mutations", () => {
    const defaults = createQueryClient().getDefaultOptions();

    expect(defaults.queries?.retry).toBe(shouldRetry);
    expect(defaults.mutations?.retry).toBe(false);
    expect(defaults.queries?.refetchOnWindowFocus).toBe(false);
  });
});
