import { memo } from "react";

import { useDelayedFlag } from "../hooks/useDelayedFlag.ts";
import { Callout } from "./Callout.tsx";

/** How long the server may take to answer before it is said to be waking up (SPEC section 7). */
export const COLD_START_AFTER_MS = 3000;

interface ServerStatusProps {
  /** The warm-up request is still waiting for an answer. */
  waking: boolean;
  /** The warm-up request gave up. */
  failed: boolean;
}

/**
 * Says what is going on when the server is slow to answer the first call, which free hosting
 * causes by putting idle servers to sleep. Silent while the server answers quickly.
 */
export const ServerStatus = memo(function ServerStatus({ waking, failed }: ServerStatusProps) {
  const slow = useDelayedFlag(waking, COLD_START_AFTER_MS);
  if (failed) {
    return (
      <Callout tone="danger" title="The server is not answering" role="alert">
        <p>
          You can still try to plan a trip; if it does not work, check your connection and reload
          the page.
        </p>
      </Callout>
    );
  }
  if (slow) {
    return (
      <Callout tone="info" title="Waking up the server…" role="status">
        <p>
          It sleeps when it has not been used for a while, so the first request can take up to a
          minute. You can fill in the form meanwhile.
        </p>
      </Callout>
    );
  }
  return null;
});
