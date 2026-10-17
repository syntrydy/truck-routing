import { useQuery } from "@tanstack/react-query";

import { useApi } from "../api/ApiProvider.tsx";

export const MIN_QUERY_LENGTH = 3;
export const MAX_QUERY_LENGTH = 100;
const ONE_DAY_MS = 24 * 60 * 60 * 1000;

/** The query as the API reads it: spacing tidied. */
export function normalizeQuery(text: string): string {
  return text.trim().split(/\s+/).join(" ");
}

/** Places matching `text`; nothing is asked until it has at least three characters. */
export function useGeocode(text: string) {
  const api = useApi();
  const query = normalizeQuery(text);
  return useQuery({
    queryKey: ["geocode", query.toLowerCase()],
    queryFn: ({ signal }) => api.geocode(query, signal),
    enabled: query.length >= MIN_QUERY_LENGTH && query.length <= MAX_QUERY_LENGTH,
    staleTime: ONE_DAY_MS, // the server keeps answers for a day too
    select: (response) => response.results,
  });
}
