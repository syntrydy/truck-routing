import { useEffect, useState } from "react";

/** Whole seconds since `active` became true, counted up while it stays true; 0 otherwise. */
export function useElapsedSeconds(active: boolean): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) {
      return;
    }
    const timer = setInterval(() => {
      setSeconds((previous) => previous + 1);
    }, 1000);
    return () => {
      clearInterval(timer);
      setSeconds(0);
    };
  }, [active]);
  return active ? seconds : 0;
}
