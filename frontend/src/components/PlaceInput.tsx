import { useState } from "react";

import type { Place } from "../api/types.ts";
import { useDebouncedValue } from "../hooks/useDebouncedValue.ts";
import { MIN_QUERY_LENGTH, normalizeQuery, useGeocode } from "../hooks/useGeocode.ts";
import { PlaceCombobox, type SearchStatus } from "./PlaceCombobox.tsx";

export const SEARCH_DELAY_MS = 300;

interface PlaceInputProps {
  id: string;
  label: string;
  /** The chosen place; `null` until one is picked from the list, and again once the text is edited. */
  value: Place | null;
  onChange: (place: Place | null) => void;
  onBlur?: () => void;
  error?: string | undefined;
}

/** A place field: searches as the user types, after a short pause, and reports the choice. */
export function PlaceInput({ id, label, value, onChange, onBlur, error }: PlaceInputProps) {
  const [text, setText] = useState(value?.label ?? "");
  // A place chosen from outside (the form switching to the demo trip) shows its name here too.
  const [seen, setSeen] = useState(value);
  if (value !== seen) {
    setSeen(value);
    if (value !== null && value.label !== text) {
      setText(value.label);
    }
  }
  const debounced = useDebouncedValue(text, SEARCH_DELAY_MS);
  // Search only for the text as it now stands, never the previous text while the pause runs out.
  const search = useGeocode(value === null && debounced === text ? debounced : "");
  const wanted = value === null && normalizeQuery(text).length >= MIN_QUERY_LENGTH;

  let status: SearchStatus = "idle";
  if (wanted) {
    if (debounced !== text || search.isFetching) {
      status = "searching";
    } else if (search.isError) {
      status = "error";
    } else if (search.data !== undefined) {
      status = search.data.length === 0 ? "empty" : "results";
    }
  }

  return (
    <PlaceCombobox
      id={id}
      label={label}
      text={text}
      onTextChange={(next) => {
        setText(next);
        if (value !== null) {
          onChange(null); // editing the text un-chooses the place
        }
      }}
      options={search.data ?? []}
      status={status}
      onSelect={(place) => {
        setText(place.label);
        onChange(place);
      }}
      onBlur={onBlur}
      error={error}
    />
  );
}
