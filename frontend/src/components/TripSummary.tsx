import { memo } from "react";

import type { PlanRequest } from "../api/types.ts";
import { summarizeTrip } from "../lib/trip.ts";
import { PencilIcon } from "./icons.tsx";

interface TripSummaryProps {
  /** The request the plan on screen was made for. */
  request: PlanRequest;
  /** The id of the form this opens, so that assistive technology can follow the link. */
  formId: string;
  onEdit: () => void;
}

/** The planned trip in one line, in place of the folded form, with a button to open it. */
export const TripSummary = memo(function TripSummary({
  request,
  formId,
  onEdit,
}: TripSummaryProps) {
  return (
    <div className="trip-summary">
      <p className="trip-summary__text">{summarizeTrip(request)}</p>
      <button
        type="button"
        className="button button--secondary button--small"
        aria-expanded="false"
        aria-controls={formId}
        onClick={onEdit}
      >
        <PencilIcon /> Edit trip
      </button>
    </div>
  );
});
