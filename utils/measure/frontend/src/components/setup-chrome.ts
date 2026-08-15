import { css, html, nothing } from "lit";
import { describe as describeMeter } from "../power-meter";
import type { MeterContext } from "../power-meter";
import type { MeasureDefinition, MeasureType, PowerMeterSpec } from "../types";

/**
 * The framing around the measurement form: choosing what to measure, restating that choice, and
 * showing which meter the measurement will read from. All presentation, no form state — rendered
 * into the setup view's own tree so it shares that view's stylesheet.
 */

export const setupChromeStyles = css`
  .type-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 0.75rem; margin: 1.25rem 0 0.25rem; }
  .type-card { display: grid; grid-template-columns: auto 1fr; grid-template-rows: auto auto; column-gap: 0.75rem; row-gap: 0.25rem; text-align: left; align-items: start; padding: 1rem; min-height: auto; background: var(--field); }
  .type-card:hover:not(:disabled) { border-color: var(--signal); }
  .type-icon { grid-row: 1 / span 2; font-size: 1.6rem; line-height: 1; }
  .type-label { font-weight: 700; color: var(--ink); }
  .type-desc { color: var(--muted); font-size: 0.82rem; font-weight: 500; line-height: 1.35; }

  .type-chip { display: flex; align-items: center; gap: 0.75rem; margin: 1.25rem 0 0.5rem; padding: 0.75rem 1rem; border: 1px solid var(--line); border-radius: 12px; background: var(--field); }
  .type-chip .type-icon { grid-row: auto; font-size: 1.4rem; }
  .type-chip .chip-body { display: grid; gap: 0.1rem; flex: 1; min-width: 0; }
  .type-chip button { min-height: 38px; padding: 0.4rem 0.9rem; }

  .power-meter-required { display: grid; justify-items: start; gap: 0.65rem; margin-top: 1.25rem; padding: 1.1rem; border: 1px solid var(--signal); border-radius: 12px; background: color-mix(in srgb, var(--signal) 8%, var(--field)); }
  .power-meter-required h3, .power-meter-required p { margin: 0; }
  .power-meter-summary { display: flex; align-items: center; gap: 0.8rem; min-width: 0; padding: 0.8rem 0.9rem; border: 1px solid var(--line); border-radius: 10px; background: var(--field); }
  .power-meter-icon { display: grid; place-items: center; flex: 0 0 auto; width: 34px; height: 34px; border-radius: 50%; background: color-mix(in srgb, var(--signal) 14%, transparent); color: var(--signal-strong); font-size: 1.05rem; }
  .power-meter-details { display: grid; gap: 0.12rem; flex: 1; min-width: 0; }
  .power-meter-details strong { overflow-wrap: anywhere; color: var(--ink); font-size: 0.84rem; }
  .power-meter-details span { overflow-wrap: anywhere; color: var(--muted); font-size: 0.78rem; line-height: 1.35; }
  .power-meter-summary button { flex: 0 0 auto; min-height: 38px; padding: 0.4rem 0.9rem; }

  @media (max-width: 640px) {
    .type-grid { grid-template-columns: 1fr; }
    .type-chip { flex-wrap: wrap; }
    .type-chip .chip-body { min-width: calc(100% - 50px); }
    .type-chip button { width: 100%; }
    .power-meter-summary { display: grid; grid-template-columns: 34px minmax(0, 1fr); align-items: start; }
    .power-meter-details { min-width: 0; }
    .power-meter-summary button { grid-column: 1 / -1; width: 100%; }
  }
`;

/** Nothing can be measured until a meter is configured, so the form is replaced by this prompt. */
export function renderPowerMeterRequired(onOpenSettings: () => void) {
  return html`
    <div class="power-meter-required">
      <h3>Set up your power meter</h3>
      <p class="muted">Choose the power source used for every measurement before creating a profile.</p>
      <button class="primary" type="button" @click=${onOpenSettings}>Set up power meter</button>
    </div>
  `;
}

export function renderTypePicker(definitions: MeasureDefinition[], onSelect: (type: MeasureType) => void) {
  if (!definitions.length) return html`<p class="muted">Loading measurement types…</p>`;
  return html`
    <p class="muted">What do you want to measure?</p>
    <div class="type-grid">
      ${definitions.map((definition) => html`
        <button type="button" class="type-card" @click=${() => onSelect(definition.measure_type)}>
          <span class="type-icon" aria-hidden="true">${definition.icon}</span>
          <span class="type-label">${definition.label}</span>
          <span class="type-desc">${definition.description}</span>
        </button>
      `)}
    </div>
  `;
}

/** The chosen type, restated compactly once the form below it has taken over the screen. */
export function renderTypeChip(type: MeasureType, definition: MeasureDefinition | undefined, onChange: () => void) {
  return html`
    <div class="type-chip">
      <span class="type-icon" aria-hidden="true">${definition?.icon ?? ""}</span>
      <span class="chip-body">
        <strong>${definition?.label ?? type}</strong>
        ${definition ? html`<span class="type-desc">${definition.description}</span>` : nothing}
      </span>
      <button type="button" aria-label="Change measurement type" @click=${onChange}>Change</button>
    </div>
  `;
}

export interface PowerMeterSummaryOptions {
  meter: PowerMeterSpec;
  measureDevice: string;
  context: MeterContext;
  onOpenSettings: () => void;
}

export function renderPowerMeterSummary(options: PowerMeterSummaryOptions) {
  const { source, detail } = describeMeter(options.meter, options.context);
  return html`
    <div class="power-meter-summary">
      <span class="power-meter-icon" aria-hidden="true">⚡</span>
      <span class="power-meter-details">
        <strong>${source}</strong>
        <span>Measurement device: ${options.measureDevice}</span>
        <span>${detail}</span>
      </span>
      <button type="button" aria-label="Change power meter" @click=${options.onOpenSettings}>Change</button>
    </div>
  `;
}
