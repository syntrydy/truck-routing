import { ApiError } from "../api/errors.ts";

interface PlanStatusProps {
  pending: boolean;
  error: Error | null;
}

/** What is happening with the plan request. The full set of states comes with a later item. */
export function PlanStatus({ pending, error }: PlanStatusProps) {
  if (pending) {
    return (
      <p className="plan-status" role="status">
        Planning your trip…
      </p>
    );
  }
  if (error !== null) {
    const requestId = error instanceof ApiError ? error.requestId : null;
    return (
      <p className="plan-status plan-status--error" role="alert">
        {error instanceof ApiError ? error.message : "Something went wrong. Please try again."}
        {requestId !== null && requestId !== "" && (
          <span className="plan-status__id"> (reference {requestId})</span>
        )}
      </p>
    );
  }
  return null;
}
