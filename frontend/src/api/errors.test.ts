import { describe, expect, it } from "vitest";

import { ApiError, parseErrorResponse } from "./errors.ts";
import { errorEnvelope, jsonResponse } from "./testing.tsx";

describe("parseErrorResponse", () => {
  it("reads the API's error envelope", async () => {
    const response = jsonResponse(
      errorEnvelope("VALIDATION", "load_lb must be a whole number", "load_lb"),
      {
        status: 400,
      },
    );

    const error = await parseErrorResponse(response);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      code: "VALIDATION",
      message: "load_lb must be a whole number",
      field: "load_lb",
      status: 400,
      requestId: "req-1",
      retryAfterS: null,
    });
  });

  it.each([
    ["TOO_CLOSE", 400],
    ["NO_ROUTE", 422],
    ["RATE_LIMITED", 429],
    ["UPSTREAM_ERROR", 502],
    ["UPSTREAM_UNAVAILABLE", 503],
    ["UPSTREAM_TIMEOUT", 504],
    ["INTERNAL_ERROR", 500],
    ["NOT_FOUND", 404],
  ])("keeps the code %s", async (code, status) => {
    const error = await parseErrorResponse(jsonResponse(errorEnvelope(code), { status }));

    expect(error.code).toBe(code);
    expect(error.status).toBe(status);
  });

  it("reads Retry-After in seconds", async () => {
    const response = jsonResponse(errorEnvelope("RATE_LIMITED"), {
      status: 429,
      headers: { "Retry-After": "60" },
    });

    expect((await parseErrorResponse(response)).retryAfterS).toBe(60);
  });

  it.each(["", "soon", "0", "-5"])("ignores the unusable Retry-After %j", async (value) => {
    const response = jsonResponse(errorEnvelope("RATE_LIMITED"), {
      status: 429,
      headers: { "Retry-After": value },
    });

    expect((await parseErrorResponse(response)).retryAfterS).toBeNull();
  });

  it("turns a code it does not know into UNKNOWN but keeps the message", async () => {
    const error = await parseErrorResponse(
      jsonResponse(errorEnvelope("BRAND_NEW", "A new problem"), { status: 418 }),
    );

    expect(error).toMatchObject({ code: "UNKNOWN", message: "A new problem", status: 418 });
  });

  it("falls back on the request ID header when the body has none", async () => {
    const body = errorEnvelope("INTERNAL_ERROR");
    body.error.request_id = "";
    const response = jsonResponse(body, {
      status: 500,
      headers: { "X-Request-ID": "from-header" },
    });

    expect((await parseErrorResponse(response)).requestId).toBe("from-header");
  });

  it("copes with a body that is not JSON, such as a proxy's error page", async () => {
    const response = new Response("<html>Bad gateway</html>", {
      status: 502,
      headers: { "X-Request-ID": "abc" },
    });

    const error = await parseErrorResponse(response);

    expect(error).toMatchObject({ code: "UNKNOWN", status: 502, requestId: "abc", field: null });
    expect(error.message).toContain("502");
  });

  it.each([
    ["an array", []],
    ["null", null],
    ["no error key", { detail: "nope" }],
    ["an error that is a string", { error: "boom" }],
    ["an error without a message", { error: { code: "NO_ROUTE", field: null, request_id: "x" } }],
    ["a numeric code", { error: { code: 5, message: "m", field: null, request_id: "x" } }],
  ])("does not trust %s", async (_name, body) => {
    const error = await parseErrorResponse(jsonResponse(body, { status: 400 }));

    expect(error.code).toBe("UNKNOWN");
    expect(error.status).toBe(400);
  });
});
