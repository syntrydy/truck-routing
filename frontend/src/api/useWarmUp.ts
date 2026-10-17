import { useQuery } from "@tanstack/react-query";

import { useApi } from "./ApiProvider";

const WARM_UP_RETRIES = 3;
const WARM_UP_RETRY_DELAY_MS = 2_000;

export const HEALTH_QUERY_KEY = ["health"] as const;

/**
 * Pings `/api/health` once when the app loads, so a sleeping server starts waking while the
 * user types. `isPending` stays true until it answers: the cold-start message hangs on it.
 */
export function useWarmUp() {
  const api = useApi();
  return useQuery({
    queryKey: HEALTH_QUERY_KEY,
    queryFn: ({ signal }) => api.health(signal),
    staleTime: Infinity,
    retry: WARM_UP_RETRIES,
    retryDelay: WARM_UP_RETRY_DELAY_MS,
  });
}
