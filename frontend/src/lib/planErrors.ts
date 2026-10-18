import { ApiError } from "../api/errors.ts";

export interface ErrorDescription {
  /** What went wrong, in a sentence. */
  title: string;
  /** What the person can do about it. */
  suggestion: string;
  /** Whether trying the same request again can help; if not, something has to change first. */
  retryable: boolean;
}

const DEFAULT_WAIT_S = 60;

/**
 * What to tell the person for a failed plan: what happened and what to do. The wording is
 * ours, not the server's, except for a validation message, which names the field at fault.
 */
export function describeError(error: unknown): ErrorDescription {
  if (!(error instanceof ApiError)) {
    return {
      title: "Something went wrong",
      suggestion: "Please try again.",
      retryable: true,
    };
  }
  switch (error.code) {
    case "VALIDATION":
      return {
        title: error.message,
        suggestion: "Correct that field and plan the trip again.",
        retryable: false,
      };
    case "TOO_CLOSE":
      return {
        title: "The start and the destination are too close together",
        suggestion: "Choose a destination at least 1 mile from the start.",
        retryable: false,
      };
    case "NO_ROUTE":
      return {
        title: "No drivable route was found between these places",
        suggestion: "Choose places on or near a road, for example a nearby town, and plan again.",
        retryable: false,
      };
    case "RATE_LIMITED": {
      const seconds = Math.ceil(error.retryAfterS ?? DEFAULT_WAIT_S);
      return {
        title: "Too many requests in a short time",
        suggestion: `Wait ${String(seconds)} seconds, then try again.`,
        retryable: true,
      };
    }
    case "UPSTREAM_ERROR":
      return {
        title: "A map or weather service returned an error",
        suggestion: "Try again in a moment.",
        retryable: true,
      };
    case "UPSTREAM_UNAVAILABLE":
      return {
        title: "A map or weather service is not available right now",
        suggestion:
          "Routes and forecasts come from outside services. Try again in a minute or two.",
        retryable: true,
      };
    case "UPSTREAM_TIMEOUT":
    case "TIMEOUT":
      return {
        title: "The request took too long",
        suggestion:
          "Try again. For a very long trip, a larger checkpoint spacing makes the request smaller.",
        retryable: true,
      };
    case "NETWORK":
      return {
        title: "The server could not be reached",
        suggestion: "Check your internet connection and try again.",
        retryable: true,
      };
    case "INVALID_RESPONSE":
      return {
        title: "The server's answer could not be read",
        suggestion: "Try again. If it keeps happening, please report the reference below.",
        retryable: true,
      };
    case "INTERNAL_ERROR":
      return {
        title: "Something went wrong on our side",
        suggestion: "Try again. If it keeps happening, please report the reference below.",
        retryable: true,
      };
    case "NOT_FOUND":
    case "UNKNOWN":
      return {
        title: "The trip could not be planned",
        suggestion: "Try again. If it keeps happening, please report the reference below.",
        retryable: true,
      };
  }
}
