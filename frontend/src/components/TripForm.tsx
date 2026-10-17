import { useId, useRef, useState, type SubmitEvent } from "react";

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
  type TripField,
  type TripValues,
} from "../lib/trip.ts";
import { PlaceInput } from "./PlaceInput.tsx";

interface TripFormProps {
  /** The request the plan on screen was made for, if any; changing an input then makes it stale. */
  planned: PlanRequest | null;
  onSubmit: (request: PlanRequest) => void;
  /** The current time; a prop so that tests can fix it. */
  now?: () => Date;
}

const FIELDS: readonly TripField[] = ["origin", "destination", "departure", "load"];

/** The trip description: two places, departure, load and checkpoint spacing. */
export function TripForm({ planned, onSubmit, now = () => new Date() }: TripFormProps) {
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

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    if (request === null) {
      reveal(...FIELDS);
      // Move focus to the first field with a problem once the messages are on screen.
      requestAnimationFrame(() => {
        form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
      });
      return;
    }
    onSubmit(request);
  };

  return (
    <form ref={form} className="trip-form" noValidate onSubmit={submit}>
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
            : "Whole pounds, 0 to 200,000. Heavy loads have stricter wind limits."}
        </p>
        {errorFor("load") !== undefined && (
          <p id={`${id}-load-error`} className="field__error">
            {errorFor("load")}
          </p>
        )}
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
      <button type="submit" className="trip-form__submit">
        {planned === null ? "Plan trip" : "Re-plan"}
      </button>
    </form>
  );
}
