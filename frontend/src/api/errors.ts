import type { components } from "./schema";

type ErrorDetail = components["schemas"]["ErrorDetail"];

/** Codes the API answers with (SPEC section 5). */
const SERVER_CODES = [
  "VALIDATION",
  "TOO_CLOSE",
  "NO_ROUTE",
  "RATE_LIMITED",
  "UPSTREAM_ERROR",
  "UPSTREAM_UNAVAILABLE",
  "UPSTREAM_TIMEOUT",
  "INTERNAL_ERROR",
  "NOT_FOUND",
] as const;

/** Codes made up here, for failures that never produced an API error body. */
type ClientCode = "NETWORK" | "TIMEOUT" | "INVALID_RESPONSE" | "UNKNOWN";

export type ApiErrorCode = (typeof SERVER_CODES)[number] | ClientCode;

function isServerCode(code: string): code is (typeof SERVER_CODES)[number] {
  return (SERVER_CODES as readonly string[]).includes(code);
}

export interface ApiErrorInit {
  code: ApiErrorCode;
  message: string;
  /** HTTP status; 0 when no response arrived. */
  status: number;
  /** Dotted path of the request field at fault, for `VALIDATION`. */
  field?: string | null;
  /** The ID the server logged the request under, for support. */
  requestId?: string | null;
  /** Seconds to wait before retrying, from `Retry-After`. */
  retryAfterS?: number | null;
  cause?: unknown;
}

/** Everything that can go wrong calling the API, in one shape the screens can switch on. */
export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number;
  readonly field: string | null;
  readonly requestId: string | null;
  readonly retryAfterS: number | null;

  constructor(init: ApiErrorInit) {
    super(init.message, { cause: init.cause });
    this.name = "ApiError";
    this.code = init.code;
    this.status = init.status;
    this.field = init.field ?? null;
    this.requestId = init.requestId ?? null;
    this.retryAfterS = init.retryAfterS ?? null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isErrorDetail(value: unknown): value is ErrorDetail {
  return (
    isRecord(value) &&
    typeof value.code === "string" &&
    typeof value.message === "string" &&
    (value.field === null || typeof value.field === "string") &&
    typeof value.request_id === "string"
  );
}

function retryAfter(response: Response): number | null {
  const seconds = Number(response.headers.get("Retry-After"));
  return Number.isFinite(seconds) && seconds > 0 ? seconds : null;
}

/**
 * The error for a non-2xx `response`: the API's error envelope when it sent one, otherwise a
 * generic error that still carries the status and the request ID header.
 */
export async function parseErrorResponse(response: Response): Promise<ApiError> {
  const headerId = response.headers.get("X-Request-ID");
  const retryAfterS = retryAfter(response);
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = undefined;
  }
  if (isRecord(body) && isErrorDetail(body.error)) {
    const { code, message, field, request_id: requestId } = body.error;
    return new ApiError({
      code: isServerCode(code) ? code : "UNKNOWN",
      message,
      status: response.status,
      field,
      requestId: requestId === "" ? headerId : requestId,
      retryAfterS,
    });
  }
  return new ApiError({
    code: "UNKNOWN",
    message: `The server answered with status ${String(response.status)}`,
    status: response.status,
    requestId: headerId,
    retryAfterS,
  });
}
