import { describe, expect, it } from "vitest";

import { ApiError, type ApiErrorCode } from "../api/errors.ts";
import { describeError } from "./planErrors.ts";

const error = (code: ApiErrorCode, extra: { message?: string; retryAfterS?: number } = {}) =>
  new ApiError({ code, message: extra.message ?? "from the server", status: 0, ...extra });

const ALL_CODES: ApiErrorCode[] = [
  "VALIDATION",
  "TOO_CLOSE",
  "NO_ROUTE",
  "RATE_LIMITED",
  "UPSTREAM_ERROR",
  "UPSTREAM_UNAVAILABLE",
  "UPSTREAM_TIMEOUT",
  "INTERNAL_ERROR",
  "NOT_FOUND",
  "NETWORK",
  "TIMEOUT",
  "INVALID_RESPONSE",
  "UNKNOWN",
];

describe("describeError", () => {
  it.each(ALL_CODES)("says what happened and what to do for %s", (code) => {
    const description = describeError(error(code));

    expect(description.title.length).toBeGreaterThan(10);
    expect(description.suggestion.length).toBeGreaterThan(10);
    expect(typeof description.retryable).toBe("boolean");
  });

  it("does not repeat the same words for different problems", () => {
    const titles = ALL_CODES.filter((code) => code !== "VALIDATION").map(
      (code) => describeError(error(code)).title,
    );

    // UPSTREAM_TIMEOUT and TIMEOUT, and NOT_FOUND and UNKNOWN, deliberately share their words.
    expect(new Set(titles).size).toBe(titles.length - 2);
  });

  it("keeps the server's sentence for a validation error, which names the field", () => {
    const description = describeError(
      error("VALIDATION", { message: "load_lb must be a whole number" }),
    );

    expect(description.title).toBe("load_lb must be a whole number");
    expect(description.retryable).toBe(false);
  });

  it.each(["TOO_CLOSE", "NO_ROUTE", "VALIDATION"] as const)(
    "does not offer to retry %s: the same trip would fail the same way",
    (code) => {
      expect(describeError(error(code)).retryable).toBe(false);
    },
  );

  it.each([
    "RATE_LIMITED",
    "UPSTREAM_ERROR",
    "UPSTREAM_UNAVAILABLE",
    "UPSTREAM_TIMEOUT",
    "TIMEOUT",
    "NETWORK",
    "INVALID_RESPONSE",
    "INTERNAL_ERROR",
    "UNKNOWN",
  ] as const)("offers to retry %s", (code) => {
    expect(describeError(error(code)).retryable).toBe(true);
  });

  it("tells the person how long to wait after a rate limit", () => {
    expect(describeError(error("RATE_LIMITED", { retryAfterS: 42 })).suggestion).toContain(
      "42 seconds",
    );
    expect(describeError(error("RATE_LIMITED", { retryAfterS: 12.2 })).suggestion).toContain(
      "13 seconds",
    );
    expect(describeError(error("RATE_LIMITED")).suggestion).toContain("60 seconds");
  });

  it("points at the connection for a network failure", () => {
    expect(describeError(error("NETWORK")).suggestion).toMatch(/internet connection/);
  });

  it("suggests a simpler trip for a timeout", () => {
    expect(describeError(error("TIMEOUT")).suggestion).toMatch(/checkpoint spacing/);
  });

  it("never shows the text of an error it does not know", () => {
    const description = describeError(new Error("TypeError: x is undefined"));

    expect(description).toEqual({
      title: "Something went wrong",
      suggestion: "Please try again.",
      retryable: true,
    });
  });

  it("does not repeat the server's wording for the codes it has its own words for", () => {
    expect(describeError(error("NO_ROUTE", { message: "secret server text" })).title).not.toContain(
      "secret",
    );
  });
});
