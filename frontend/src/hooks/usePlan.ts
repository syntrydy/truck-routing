import { useMutation } from "@tanstack/react-query";

import { useApi } from "../api/ApiProvider.tsx";
import type { PlanRequest } from "../api/types.ts";

/** What to plan: the form's trip, or the recorded storm with that form's load and spacing. */
export interface PlanCall {
  kind: "trip" | "demo";
  request: PlanRequest;
}

/** Plans a trip. Call `mutate` with the call to make; `data` is the plan once it is in. */
export function usePlan() {
  const api = useApi();
  return useMutation({
    mutationFn: ({ kind, request }: PlanCall) =>
      kind === "demo" ? api.demo(request) : api.plan(request),
  });
}
