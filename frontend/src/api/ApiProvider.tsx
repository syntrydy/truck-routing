import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";

import { createApiClient, type ApiClient } from "./client";

const ApiContext = createContext<ApiClient | null>(null);

interface ApiProviderProps {
  client: ApiClient;
  queryClient: QueryClient;
  children: ReactNode;
}

/** Gives the components below the API client and the query cache. */
export function ApiProvider({ client, queryClient, children }: ApiProviderProps) {
  return (
    <ApiContext value={client}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ApiContext>
  );
}

export function useApi(): ApiClient {
  const client = useContext(ApiContext);
  if (client === null) {
    throw new Error("useApi must be used inside an ApiProvider");
  }
  return client;
}

/** The client for the deployed API: `VITE_API_BASE_URL`, or the same origin when it is unset. */
export function createDefaultApiClient(): ApiClient {
  return createApiClient({ baseUrl: import.meta.env.VITE_API_BASE_URL ?? "" });
}
