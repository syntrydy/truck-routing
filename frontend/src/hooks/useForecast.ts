import { useEffect, useState } from "react";

import type { PlanResponse } from "../api/types.ts";
import type { HeatmapVariable } from "../lib/heatmap.ts";
import { useHeatmapFrames } from "./useHeatmapFrames.ts";

/** One hour of playback, in milliseconds (SPEC section 7). */
export const PLAY_STEP_MS = 400;

interface State {
  /** The plan this state belongs to; a new plan starts again from the first hour. */
  plan: PlanResponse | null;
  hour: number;
  playing: boolean;
  variable: HeatmapVariable;
}

const INITIAL: State = { plan: null, hour: 0, playing: false, variable: "risk" };

/**
 * The state of the forecast control: which hour is shown, whether it is playing, and which
 * variable is mapped. A new plan resets the hour and stops playback; the variable is kept.
 */
export function useForecast(plan: PlanResponse | null) {
  const [stored, setStored] = useState<State>(INITIAL);
  const current: State =
    stored.plan === plan ? stored : { ...stored, plan, hour: 0, playing: false };
  const maxHour = Math.max(0, (plan?.heatmap.frames.length ?? 1) - 1);
  const frames = useHeatmapFrames(plan, current.variable);

  useEffect(() => {
    if (!current.playing) {
      return;
    }
    const timer = setInterval(() => {
      setStored((previous) => {
        if (previous.plan !== plan) {
          return previous;
        }
        const next = previous.hour + 1;
        return next >= maxHour
          ? { ...previous, hour: maxHour, playing: false }
          : { ...previous, hour: next };
      });
    }, PLAY_STEP_MS);
    return () => {
      clearInterval(timer);
    };
  }, [current.playing, plan, maxHour]);

  /** Changes the state of this plan; functional, so several changes in one event all apply. */
  const update = (change: (state: State) => State) => {
    setStored((previous) =>
      change(previous.plan === plan ? previous : { ...previous, plan, hour: 0, playing: false }),
    );
  };

  return {
    frames,
    hour: current.hour,
    maxHour,
    playing: current.playing,
    variable: current.variable,
    setHour: (hour: number) => {
      const whole = Math.min(Math.max(Math.round(hour), 0), maxHour);
      update((state) => ({ ...state, hour: whole, playing: false }));
    },
    setVariable: (variable: HeatmapVariable) => {
      update((state) => ({ ...state, variable }));
    },
    /** Starts playing, from the beginning if the end was reached; or pauses. */
    togglePlay: () => {
      update((state) => {
        if (state.playing) {
          return { ...state, playing: false };
        }
        if (maxHour === 0) {
          return state;
        }
        return { ...state, hour: state.hour >= maxHour ? 0 : state.hour, playing: true };
      });
    },
  };
}
