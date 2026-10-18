import { memo } from "react";

import { ApiError } from "../api/errors.ts";
import type { PlanResponse } from "../api/types.ts";
import { describeError } from "../lib/planErrors.ts";
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
      <div className="plan-status plan-status--error" role="alert">
        <p className="plan-status__title">{title}</p>
        <p>{suggestion}</p>
        {reference !== null && reference !== "" && (
          <p className="plan-status__id">Reference: {reference}</p>
        )}
        {retryable && (
          <button type="button" className="plan-status__retry" onClick={onRetry}>
            Try again
          </button>
        )}
      </div>
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
