import { type SubmitEvent, memo, useId, useRef, useState } from "react";

import type { PlanRequest } from "../api/types.ts";
import {
  defaultTripValues,
  HEAVY_LOAD_LB,
  INTERVALS,
  isStale,
  parseLoad,
  timeZoneLabel,
  toPlanRequest,
  validateTrip,
  withDemoTrip,
  type TripField,
  type TripValues,
} from "../lib/trip.ts";
import { StormIcon, SwapIcon } from "./icons.tsx";
import { PlaceInput } from "./PlaceInput.tsx";

interface TripFormProps {
  /** The request the plan on screen was made for, if any; changing an input then makes it stale. */
  planned: PlanRequest | null;
  onSubmit: (request: PlanRequest) => void;
  /** The stormy demo, with the form set to the demo trip; only its load and spacing are used. */
  onDemo: (request: PlanRequest) => void;
  /** The current time; a prop so that tests can fix it. */
  now?: () => Date;
}

const FIELDS: readonly TripField[] = ["origin", "destination", "departure", "load"];

/** The trip description: two places, departure, load and checkpoint spacing. */
export const TripForm = memo(function TripForm({
  planned,
  onSubmit,
  onDemo,
  now = () => new Date(),
}: TripFormProps) {
  const id = useId();
  const form = useRef<HTMLFormElement>(null);
  const [values, setValues] = useState<TripValues>(() => defaultTripValues(now()));
  const [shown, setShown] = useState<ReadonlySet<TripField>>(new Set());

  const current = now();
  const errors = validateTrip(values, current);
  const request = toPlanRequest(values, current);
  const stale = isStale(planned, request);
  const load = parseLoad(values.load);

  const update = (changes: Partial<TripValues>) => {
    setValues((previous) => ({ ...previous, ...changes }));
  };
  const reveal = (...fields: TripField[]) => {
    setShown((previous) => new Set([...previous, ...fields]));
  };
  const errorFor = (field: TripField) => (shown.has(field) ? errors[field] : undefined);

  /** Send `next` on with `send`, or show what is wrong with it and focus the first problem. */
  const sendOrShowProblems = (next: PlanRequest | null, send: (request: PlanRequest) => void) => {
    if (next === null) {
      reveal(...FIELDS);
      // Move focus to the first field with a problem once the messages are on screen.
      requestAnimationFrame(() => {
        form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
      });
      return;
    }
    send(next);
  };

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    sendOrShowProblems(request, onSubmit);
  };

  const demo = () => {
    const next = withDemoTrip(values, current);
    setValues(next);
    sendOrShowProblems(toPlanRequest(next, current), onDemo);
  };

  const canSwap = values.origin !== null && values.destination !== null;
  const swap = () => {
    update({ origin: values.destination, destination: values.origin });
  };

  return (
    <form ref={form} className="trip-form" noValidate onSubmit={submit}>
      <div className="demo-card">
        <span className="demo-card__icon">
          <StormIcon />
        </span>
        <div className="demo-card__body">
          <p className="demo-card__title">No storm today?</p>
          <p id={`${id}-demo-hint`} className="demo-card__hint">
            See High, Severe and No Travel at work: Denver to Salt Lake City in a recording of a
            real wind storm on I-80 in Wyoming. Not a live forecast.
          </p>
          <button
            type="button"
            className="button button--demo"
            aria-describedby={`${id}-demo-hint`}
            onClick={demo}
          >
            Try the stormy demo
          </button>
        </div>
      </div>

      <div className="route-pair">
        <div className="route-pair__row route-pair__row--start">
          <PlaceInput
            id={`${id}-origin`}
            label="From"
            value={values.origin}
            onChange={(origin) => {
              update({ origin });
            }}
            onBlur={() => {
              reveal("origin");
            }}
            error={errorFor("origin")}
          />
        </div>
        <div className="route-pair__row route-pair__row--end">
          <PlaceInput
            id={`${id}-destination`}
            label="To"
            value={values.destination}
            onChange={(destination) => {
              update({ destination });
            }}
            onBlur={() => {
              reveal("destination");
            }}
            error={errorFor("destination")}
          />
        </div>
        <button
          type="button"
          className="route-pair__swap"
          aria-label="Swap start and destination"
          disabled={!canSwap}
          onClick={swap}
        >
          <SwapIcon />
        </button>
      </div>

      <div className="trip-form__when">
        <div className="field">
          <label htmlFor={`${id}-departure`}>Departure</label>
          <input
            id={`${id}-departure`}
            type="datetime-local"
            value={values.departure}
            aria-invalid={errorFor("departure") !== undefined}
            aria-describedby={`${id}-departure-hint${errorFor("departure") === undefined ? "" : ` ${id}-departure-error`}`}
            onChange={(event) => {
              update({ departure: event.target.value });
            }}
            onBlur={() => {
              reveal("departure");
            }}
          />
          <p id={`${id}-departure-hint`} className="field__hint">
            Time zone: {timeZoneLabel(current)}
          </p>
          {errorFor("departure") !== undefined && (
            <p id={`${id}-departure-error`} className="field__error">
              {errorFor("departure")}
            </p>
          )}
        </div>

        <div className="field">
          <label htmlFor={`${id}-load`}>Load (lb)</label>
          <input
            id={`${id}-load`}
            type="text"
            inputMode="numeric"
            autoComplete="off"
            value={values.load}
            aria-invalid={errorFor("load") !== undefined}
            aria-describedby={`${id}-load-hint${errorFor("load") === undefined ? "" : ` ${id}-load-error`}`}
            onChange={(event) => {
              update({ load: event.target.value });
            }}
            onBlur={() => {
              reveal("load");
            }}
          />
          <p id={`${id}-load-hint`} className="field__hint">
            {load !== null && load > HEAVY_LOAD_LB
              ? `A load above ${HEAVY_LOAD_LB.toLocaleString("en-US")} lb exceeds the usual legal limit.`
              : "0 to 200,000 lb. Heavier loads get stricter wind limits."}
          </p>
          {errorFor("load") !== undefined && (
            <p id={`${id}-load-error`} className="field__error">
              {errorFor("load")}
            </p>
          )}
        </div>
      </div>

      <fieldset className="segmented">
        <legend>Checkpoint every</legend>
        {INTERVALS.map((miles) => (
          <label key={miles} className="segmented__option">
            <input
              type="radio"
              name={`${id}-interval`}
              value={miles}
              checked={values.interval === miles}
              onChange={() => {
                update({ interval: miles });
              }}
            />
            <span>{miles} mi</span>
          </label>
        ))}
      </fieldset>

      {stale && (
        <p className="trip-form__stale" role="status">
          Inputs changed — re-plan
        </p>
      )}
      <button type="submit" className="button button--primary">
        {planned === null ? "Plan trip" : "Re-plan"}
      </button>
    </form>
  );
});
