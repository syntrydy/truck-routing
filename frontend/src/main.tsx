import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { ApiProvider, createDefaultApiClient } from "./api/ApiProvider.tsx";
import { createQueryClient } from "./api/queryClient.ts";
import { App } from "./App.tsx";
import "./styles.css";

const apiClient = createDefaultApiClient();
const queryClient = createQueryClient();

const container = document.getElementById("root");
if (container === null) {
  throw new Error("Root element #root not found");
}

createRoot(container).render(
  <StrictMode>
    <ApiProvider client={apiClient} queryClient={queryClient}>
      <App />
    </ApiProvider>
  </StrictMode>,
);
