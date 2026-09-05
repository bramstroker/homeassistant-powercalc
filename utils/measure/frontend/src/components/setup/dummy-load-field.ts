import { css, html, nothing } from "lit";
import { calibrationDate, resistance } from "../../utils/format";
import type { DummyLoadCalibration, DummyLoadSpec } from "../../types";
import { textField } from "../shared/fields";

/**
 * The resistive dummy load a measurement can be corrected against.
 *
 * Rendered into the surrounding form's own tree rather than as a custom element, because its
 * inputs have to take part in that form's submission. The owning view holds the two pieces of
 * state and passes them back in.
 */

export interface DummyLoadOptions {
  /** The calibration already on file, when the app has one. */
  calibration: DummyLoadCalibration | null;
  /** What a previous run of this measurement used, when the draft came from one. */
  stored?: DummyLoadSpec | null;
  enabled: boolean;
  mode: DummyLoadSpec["mode"];
  /** Correction needs a voltage reading, so without one the whole option is unavailable. */
  voltageAvailable: boolean;
  onToggle: (event: Event) => void;
  onModeChange: (event: Event) => void;
}

export const dummyLoadStyles = css`
  .dummy-load { display: grid; gap: 0.9rem; }
  .dummy-load-toggle { width: fit-content; }
  .dummy-load-options { display: grid; gap: 0.8rem; padding: 0.9rem; border: 1px solid var(--line); border-radius: 10px; background: var(--field); }
  .dummy-load-options p { margin: 0; }
  .calibration-card { display: grid; gap: 0.2rem; }
  .calibration-card strong { color: var(--ink); }
  .calibration-meta { color: var(--muted); font-size: 0.78rem; }
  .choice-list { display: grid; gap: 0.5rem; }
  .choice { display: flex; grid-template-columns: none; align-items: flex-start; gap: 0.55rem; color: var(--ink); }
  .choice input { width: auto; min-height: auto; margin-top: 0.2rem; accent-color: var(--signal); }
`;

export function renderDummyLoad(options: DummyLoadOptions) {
  const { enabled, voltageAvailable } = options;
  return html`
    <div class="dummy-load">
      <label class="check dummy-load-toggle">
        <input type="checkbox" name="use_dummy_load" .checked=${enabled} ?disabled=${!voltageAvailable} @change=${options.onToggle} />
        Use resistive dummy load
      </label>
      ${voltageAvailable
        ? nothing
        : html`<p class="muted">Dummy-load correction requires a voltage sensor associated with the selected power sensor.</p>`}
      ${enabled && voltageAvailable ? renderOptions(options) : nothing}
    </div>
  `;
}

/** The mode a fresh form should start in: reuse the saved calibration when there is one. */
export function defaultDummyLoadMode(calibration: DummyLoadCalibration | null): DummyLoadSpec["mode"] {
  return calibration ? "reuse" : "calibrate";
}

function renderOptions({ calibration, stored, mode, onModeChange }: DummyLoadOptions) {
  return html`
    <div class="dummy-load-options">
      ${calibration ? renderCalibrationChoice(calibration, mode, onModeChange) : renderInlineCalibration()}
      ${mode === "calibrate"
        ? textField("dummy_load_description", "Dummy-load description", {
          value: stored?.description ?? calibration?.description ?? "",
          placeholder: "e.g. 60 W incandescent bulb",
          required: true,
          hint: "Identify the exact resistive load so the calibration can be safely reused later.",
        })
        : nothing}
    </div>
  `;
}

function renderCalibrationChoice(
  calibration: DummyLoadCalibration,
  mode: DummyLoadSpec["mode"],
  onModeChange: (event: Event) => void,
) {
  const choice = (value: DummyLoadSpec["mode"], title: string, explanation: string) => html`
    <label class="choice">
      <input type="radio" name="dummy_load_mode" value=${value} .checked=${mode === value} @change=${onModeChange} />
      <span><strong>${title}</strong><br /><small class="field-hint">${explanation}</small></span>
    </label>
  `;
  return html`
    <div class="calibration-card">
      <strong>${calibration.description}</strong>
      <span class="calibration-meta">
        ${resistance(calibration.resistance)} Ω · calibrated ${calibrationDate(calibration.calibrated_at)}
      </span>
    </div>
    <div class="choice-list" role="radiogroup" aria-label="Dummy-load calibration">
      ${choice("reuse", "Use saved calibration", "Confirm that this exact, preheated load is connected when the measurement starts.")}
      ${choice("calibrate", "Recalibrate", "Measure the load again before starting this measurement.")}
    </div>
  `;
}

function renderInlineCalibration() {
  return html`
    <input type="hidden" name="dummy_load_mode" value="calibrate" />
    <p class="muted">
      The dummy load will be calibrated inline before the measurement.
      Allow at least 10 minutes; an unstable load can take longer.
    </p>
  `;
}
