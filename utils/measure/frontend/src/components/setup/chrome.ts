import { css, html } from "lit";
import { describe as describeMeter } from "../../power-meter";
import type { MeterContext } from "../../power-meter";
import type { MeasureDefinition, MeasureType, PowerMeterSpec } from "../../types";

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

  .setup-summary { display: grid; gap: 0.5rem; margin: 1.25rem 0 1.5rem; padding-bottom: 1rem; border-bottom: 1px solid var(--line); }
  .type-chip { display: flex; align-items: center; gap: 0.75rem; min-width: 0; }
  .type-chip .type-icon { grid-row: auto; font-size: 1.4rem; }
  .type-chip .chip-body { display: grid; gap: 0.1rem; flex: 1; min-width: 0; }
  .type-chip button { min-height: 38px; padding: 0.4rem 0.9rem; }

  .power-meter-required { display: grid; justify-items: start; gap: 0.65rem; margin-top: 1.25rem; padding: 1.1rem; border: 1px solid var(--signal); border-radius: 12px; background: color-mix(in srgb, var(--signal) 8%, var(--field)); }
  .power-meter-required h3, .power-meter-required p { margin: 0; }
  .power-meter-summary { display: flex; align-items: center; gap: 0.75rem; min-width: 0; }
  .power-meter-icon, .type-chip .type-icon { display: grid; place-items: center; flex: 0 0 28px; width: 28px; }
  .power-meter-icon { color: var(--signal-strong); font-size: 1.05rem; }
  .power-meter-details { display: grid; gap: 0.12rem; flex: 1; min-width: 0; }
  .power-meter-details strong { overflow-wrap: anywhere; color: var(--ink); font-size: 0.84rem; }
  .power-meter-details span { overflow-wrap: anywhere; color: var(--muted); font-size: 0.78rem; line-height: 1.35; }
  .power-meter-details .power-meter-meta { display: flex; flex-wrap: wrap; column-gap: 1rem; row-gap: 0.12rem; }
  .power-meter-summary button { flex: 0 0 auto; min-height: 38px; padding: 0.4rem 0.9rem; }

  @media (max-width: 640px) {
    .type-grid { grid-template-columns: 1fr; }
    .type-chip, .power-meter-summary { gap: 0.5rem; }
    .type-chip button, .power-meter-summary button { padding: 0.4rem 0.6rem; }
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
        <span class="power-meter-meta">
          <span>Measurement device: ${options.measureDevice}</span>
          <span>${detail}</span>
        </span>
      </span>
      <button type="button" aria-label="Change power meter" @click=${options.onOpenSettings}>Change</button>
    </div>
  `;
}
