import { useElapsedSeconds } from "../hooks/useElapsedSeconds.ts";

/**
 * The stages of planning and when each is likely over. The server answers once, so there is no
 * real progress to show: the steps follow the time that has passed, and the text says so.
 */
export const STEPS = [
  { label: "Finding routes", untilS: 4 },
  { label: "Checking the weather along each route", untilS: 14 },
  { label: "Building the forecast", untilS: Infinity },
] as const;

/** The step that is under way after `seconds`. */
export function currentStep(seconds: number): number {
  const index = STEPS.findIndex((step) => seconds < step.untilS);
  return index === -1 ? STEPS.length - 1 : index;
}

/** Shown while a plan is being worked out. */
export function PlanProgress() {
  const seconds = useElapsedSeconds(true);
  const current = currentStep(seconds);
  return (
    <div className="progress" role="status">
      <p className="progress__title">Planning your trip…</p>
      <ol className="progress__steps">
        {STEPS.map((step, index) => {
          const state = index < current ? "done" : index === current ? "in progress" : "waiting";
          return (
            <li
              key={step.label}
              className={`progress__step progress__step--${state.replace(" ", "-")}`}
            >
              <span aria-hidden="true" className="progress__mark">
                {state === "done" ? "✓" : state === "in progress" ? "…" : "○"}
              </span>
              {step.label} <span className="visually-hidden">({state})</span>
            </li>
          );
        })}
      </ol>
      <p className="progress__note">
        This usually takes 5 to 15 seconds. The steps are an estimate.
      </p>
    </div>
  );
}
