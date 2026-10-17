import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { apiWrapper, stubClient } from "./api/testing.tsx";
import { App } from "./App.tsx";

describe("App", () => {
  it("renders the application title", () => {
    const health = vi.fn(() => Promise.resolve({ status: "ok" }));

    render(<App />, { wrapper: apiWrapper(stubClient({ health })) });

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Weather-Aware Truck Routing",
    );
  });

  it("warms the server up on load", async () => {
    const health = vi.fn(() => Promise.resolve({ status: "ok" }));

    render(<App />, { wrapper: apiWrapper(stubClient({ health })) });

    await waitFor(() => {
      expect(health).toHaveBeenCalledTimes(1);
    });
  });
});
