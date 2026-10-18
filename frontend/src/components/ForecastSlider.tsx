import { useId } from "react";

import { formatMoment, formatHoursAhead, frameTime } from "../lib/forecastTime.ts";
import { HEATMAP_VARIABLES, type HeatmapVariable } from "../lib/heatmap.ts";
import { HeatmapLegend } from "./HeatmapLegend.tsx";

interface ForecastSliderProps {
  /** The time of the first frame (ISO 8601); the frames are an hour apart. */
  startIso: string;
  hour: number;
  maxHour: number;
  playing: boolean;
  variable: HeatmapVariable;
  onHourChange: (hour: number) => void;
  onTogglePlay: () => void;
  onVariableChange: (variable: HeatmapVariable) => void;
}

/** The forecast control: an hour slider with play and pause, and the variable to map. */
export function ForecastSlider({
  startIso,
  hour,
  maxHour,
  playing,
  variable,
  onHourChange,
  onTogglePlay,
  onVariableChange,
}: ForecastSliderProps) {
  const id = useId();
  const time = `${formatMoment(frameTime(startIso, hour))}, ${formatHoursAhead(hour)}`;
  return (
    <div className="forecast">
      <div className="forecast__row">
        <button
          type="button"
          className="forecast__play"
          aria-pressed={playing}
          onClick={onTogglePlay}
        >
          <span aria-hidden="true">{playing ? "⏸" : "▶"}</span> {playing ? "Pause" : "Play"}
        </button>
        <label htmlFor={`${id}-hour`} className="visually-hidden">
          Forecast hour
        </label>
        <input
          id={`${id}-hour`}
          className="forecast__range"
          type="range"
          min={0}
          max={maxHour}
          step={1}
          value={hour}
          aria-valuetext={time}
          onChange={(event) => {
            onHourChange(Number(event.target.value));
          }}
        />
        <span className="forecast__time">{time}</span>
      </div>
      <div className="forecast__row forecast__row--wrap">
        <fieldset className="segmented forecast__variables">
          <legend>Map shows</legend>
          {HEATMAP_VARIABLES.map((option) => (
            <label key={option.id} className="segmented__option">
              <input
                type="radio"
                name={`${id}-variable`}
                value={option.id}
                checked={variable === option.id}
                onChange={() => {
                  onVariableChange(option.id);
                }}
              />
              <span>{option.label}</span>
            </label>
          ))}
        </fieldset>
        <HeatmapLegend variable={variable} />
      </div>
    </div>
  );
}
