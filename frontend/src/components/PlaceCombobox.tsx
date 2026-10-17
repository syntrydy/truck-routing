import { useState, type KeyboardEvent } from "react";

import type { Place } from "../api/types.ts";

export type SearchStatus = "idle" | "searching" | "empty" | "error" | "results";

interface PlaceComboboxProps {
  id: string;
  label: string;
  text: string;
  onTextChange: (text: string) => void;
  options: readonly Place[];
  status: SearchStatus;
  onSelect: (place: Place) => void;
  onBlur?: () => void;
  /** The validation message to show under the field. */
  error?: string | undefined;
}

const STATUS_MESSAGES: Record<Exclude<SearchStatus, "idle" | "results">, string> = {
  searching: "Searching…",
  empty: "No places found. Try a different spelling.",
  error: "Place search is unavailable right now. Try again in a moment.",
};

/**
 * A text field with a list of suggestions, following the ARIA 1.2 combobox pattern: focus
 * stays in the field, the arrow keys move through the list, Enter picks, Escape closes.
 */
export function PlaceCombobox({
  id,
  label,
  text,
  onTextChange,
  options,
  status,
  onSelect,
  onBlur,
  error,
}: PlaceComboboxProps) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const listId = `${id}-list`;
  const statusId = `${id}-status`;
  const errorId = `${id}-error`;
  const showList = open && status === "results" && options.length > 0;
  const message = status === "idle" || status === "results" ? "" : STATUS_MESSAGES[status];
  const announcement =
    showList && options.length > 0
      ? `${String(options.length)} ${options.length === 1 ? "place" : "places"} found`
      : message;

  const choose = (place: Place) => {
    onSelect(place);
    setOpen(false);
    setActive(-1);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    switch (event.key) {
      case "ArrowDown":
      case "ArrowUp": {
        if (status !== "results" || options.length === 0) {
          return;
        }
        event.preventDefault();
        setOpen(true);
        const step = event.key === "ArrowDown" ? 1 : -1;
        setActive((current) => (current + step + options.length) % options.length);
        break;
      }
      case "Enter": {
        const place = showList ? options[active] : undefined;
        if (place !== undefined) {
          event.preventDefault(); // choosing is not submitting the form
          choose(place);
        }
        break;
      }
      case "Escape":
        if (showList) {
          event.preventDefault();
          setOpen(false);
          setActive(-1);
        }
        break;
      default:
        break;
    }
  };

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        role="combobox"
        autoComplete="off"
        maxLength={100}
        value={text}
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={
          showList && active >= 0 ? `${id}-option-${String(active)}` : undefined
        }
        aria-invalid={error !== undefined}
        aria-describedby={[statusId, error === undefined ? null : errorId]
          .filter(Boolean)
          .join(" ")}
        onChange={(event) => {
          onTextChange(event.target.value);
          setOpen(true);
          setActive(-1);
        }}
        onFocus={() => {
          setOpen(true);
        }}
        onBlur={() => {
          setOpen(false);
          setActive(-1);
          onBlur?.();
        }}
        onKeyDown={onKeyDown}
      />
      <div id={listId} role="listbox" aria-label={`${label} suggestions`} hidden={!showList}>
        {showList &&
          options.map((place, index) => (
            // Focus stays in the input and the keyboard drives the list through
            // aria-activedescendant, so the options themselves take neither focus nor keys.
            // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/interactive-supports-focus
            <div
              key={`${place.label}|${String(place.lat)}|${String(place.lon)}`}
              id={`${id}-option-${String(index)}`}
              role="option"
              aria-selected={index === active}
              className={index === active ? "option option--active" : "option"}
              onMouseDown={(event) => {
                event.preventDefault(); // keep focus in the field
              }}
              onClick={() => {
                choose(place);
              }}
              onMouseEnter={() => {
                setActive(index);
              }}
            >
              <span>{place.label}</span> <span className="option__kind">{place.kind}</span>
            </div>
          ))}
      </div>
      <p id={statusId} className="field__status" role="status">
        {announcement}
      </p>
      {error !== undefined && (
        <p id={errorId} className="field__error">
          {error}
        </p>
      )}
    </div>
  );
}
