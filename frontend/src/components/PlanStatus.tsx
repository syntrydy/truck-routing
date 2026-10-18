import { memo } from "react";

import { ApiError } from "../api/errors.ts";
import type { PlanResponse } from "../api/types.ts";
import { describeError } from "../lib/planErrors.ts";
import { Callout } from "./Callout.tsx";
import { PlanProgress } from "./PlanProgress.tsx";

interface PlanStatusProps {
  pending: boolean;
  error: Error | null;
  /** The plan that arrived, so that its arrival can be announced. */
  plan: PlanResponse | null;
  onRetry: () => void;
}

/** What is happening with the plan request: working, failed (and what to do), or done. */
export const PlanStatus = memo(function PlanStatus({
  pending,
  error,
  plan,
  onRetry,
}: PlanStatusProps) {
  if (pending) {
    return <PlanProgress />;
  }
  if (error !== null) {
    const { title, suggestion, retryable } = describeError(error);
    const reference = error instanceof ApiError ? error.requestId : null;
    return (
      <Callout tone="danger" title={title} role="alert">
        <p>{suggestion}</p>
        {reference !== null && reference !== "" && (
          <p className="callout__reference">Reference: {reference}</p>
        )}
        {retryable && (
          <button type="button" className="button button--secondary" onClick={onRetry}>
            Try again
          </button>
        )}
      </Callout>
    );
  }
  if (plan !== null) {
    const best = plan.routes.find((route) => route.id === plan.recommended_route_id);
    const count = plan.routes.length;
    return (
      <p className="visually-hidden" role="status">
        {`Planned ${String(count)} ${count === 1 ? "route" : "routes"}.`}
        {best === undefined ? " None is recommended." : ` ${best.label} is recommended.`}
      </p>
    );
  }
  return null;
});
