import { useMutation } from "@tanstack/react-query";

import { useApi } from "../api/ApiProvider.tsx";
import type { PlanRequest } from "../api/types.ts";

/** Plans a trip. Call `mutate` with the form's request; `data` is the plan once it is in. */
export function usePlan() {
  const api = useApi();
  return useMutation({ mutationFn: (request: PlanRequest) => api.plan(request) });
}
