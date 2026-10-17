import { renderHook, waitFor } from "@testing-library/react";
import { StrictMode, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { ApiClient } from "./client.ts";
import { useApi } from "./ApiProvider.tsx";
import { apiWrapper, stubClient } from "./testing.tsx";
import { useWarmUp } from "./useWarmUp.ts";

describe("useWarmUp", () => {
  it("pings the health endpoint and reports the answer", async () => {
    const health = vi.fn(() => Promise.resolve({ status: "ok" }));

    const { result } = renderHook(() => useWarmUp(), {
      wrapper: apiWrapper(stubClient({ health })),
    });

    expect(result.current.isPending).toBe(true);
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toEqual({ status: "ok" });
  });

  it("sends a single request even when the app mounts twice", async () => {
    const health = vi.fn(() => Promise.resolve({ status: "ok" }));
    const Wrapper = apiWrapper(stubClient({ health }));

    const { result } = renderHook(() => useWarmUp(), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <StrictMode>
          <Wrapper>{children}</Wrapper>
        </StrictMode>
      ),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(health).toHaveBeenCalledTimes(1);
  });

  it("passes a cancellation signal to the request", async () => {
    const health = vi.fn<ApiClient["health"]>(() => Promise.resolve({ status: "ok" }));

    renderHook(() => useWarmUp(), { wrapper: apiWrapper(stubClient({ health })) });

    await waitFor(() => {
      expect(health).toHaveBeenCalled();
    });
    expect(health.mock.calls[0]?.[0]).toBeInstanceOf(AbortSignal);
  });
});

describe("useApi", () => {
  it("refuses to work outside a provider", () => {
    const quiet = vi.spyOn(console, "error").mockImplementation(() => undefined);

    expect(() => renderHook(() => useApi())).toThrow("ApiProvider");

    quiet.mockRestore();
  });
});
