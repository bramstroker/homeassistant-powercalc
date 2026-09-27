import { css, html } from "lit";
import { describe as describeMeter } from "../../power-meter/registry";
import type { MeterContext } from "../../power-meter/registry";
import type { PowerMeterSpec } from "../../types";
import type { DeviceChoice, MeasurementRoute } from "./device-routes";
import { deviceIcon } from "./device-icons";

/**
 * The framing around the measurement form: choosing what to measure, restating that choice, and
 * showing which meter the measurement will read from. All presentation, no form state — rendered
 * into the setup view's own tree so it shares that view's stylesheet.
 */

export const setupChromeStyles = css`
  .type-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 0.75rem; margin: 1.25rem 0 0.25rem; }
  .type-card { display: grid; gap: 0.25rem; text-align: left; align-items: start; padding: 1rem; min-height: auto; background: var(--field); }
  .type-card:hover:not(:disabled) { border-color: var(--signal); }
  .device-card, .device-choice { grid-template-columns: 1.6rem 1fr; align-items: center; column-gap: 0.65rem; }
  .device-choice .type-desc { grid-column: 2; }
  .device-icon { display: grid; place-items: center; width: 1.35rem; height: 1.35rem; color: var(--ink); }
  .device-icon svg, .power-meter-icon svg { display: block; width: 1.25rem; height: 1.25rem; }
  .type-label { font-weight: 700; color: var(--ink); }
  .type-desc { color: var(--muted); font-size: 0.82rem; font-weight: 500; line-height: 1.35; }
  .device-search { display: grid; gap: 0.4rem; max-width: 30rem; margin-top: 1rem; }
  .free-measurement { margin-top: 1.5rem; }

  .setup-summary { display: grid; gap: 0.5rem; margin: 1.25rem 0 1.5rem; padding-bottom: 1rem; border-bottom: 1px solid var(--line); }
  .type-chip { display: flex; align-items: center; gap: 0.75rem; min-width: 0; }
  .type-chip .device-icon { display: grid; place-items: center; flex: 0 0 28px; width: 28px; }
  .type-chip .chip-body { display: grid; gap: 0.1rem; flex: 1; min-width: 0; }
  .type-chip button { min-height: 38px; padding: 0.4rem 0.9rem; }
  .selection-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }

  .power-meter-required { display: grid; justify-items: start; gap: 0.65rem; margin-top: 1.25rem; padding: 1.1rem; border: 1px solid var(--signal); border-radius: 12px; background: color-mix(in srgb, var(--signal) 8%, var(--field)); }
  .power-meter-required h3, .power-meter-required p { margin: 0; }
  .power-meter-summary { display: flex; align-items: center; gap: 0.75rem; min-width: 0; }
  .power-meter-icon { display: grid; place-items: center; flex: 0 0 28px; width: 28px; }
  .power-meter-icon { color: var(--ink); }
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

export function renderDevicePicker(
  devices: DeviceChoice[],
  search: string,
  onSearch: (value: string) => void,
  onSelect: (deviceId: string) => void,
  hasFreeMeasurement: boolean,
) {
  if (!devices.length && !hasFreeMeasurement) return html`<p class="muted">Loading devices…</p>`;
  const matches = devices.filter((device) => device.label.toLowerCase().includes(search.trim().toLowerCase()));
  return html`
    <p class="muted">What type of device do you want to measure?</p>
    <label class="device-search"><span>Find a device type</span>
      <input type="search" .value=${search} @input=${(event: Event) => onSearch((event.target as HTMLInputElement).value)} />
    </label>
    <div class="type-grid">
      ${matches.map((device) => html`
        <button type="button" class="type-card device-card" @click=${() => onSelect(device.id)}>
          <span class="device-icon" aria-hidden="true">${deviceIcon(device.id)}</span>
          <span class="type-label">${device.label}</span>
        </button>
      `)}
    </div>
    ${!matches.length ? html`<p class="muted">No matching device types.</p>` : ""}
    ${hasFreeMeasurement ? html`<div class="free-measurement">
      <button type="button" class="type-card device-choice" @click=${() => onSelect("free_measurement")}>
        <span class="device-icon" aria-hidden="true">${deviceIcon("free_measurement")}</span>
        <span class="type-label">Free measurement</span>
        <span class="type-desc">Measure average power or record a Playbook cycle.</span>
      </button>
    </div>` : ""}
  `;
}

export function renderRoutePicker(device: DeviceChoice, routes: MeasurementRoute[], onSelect: (routeId: string) => void, onBack: () => void) {
  return html`
    <p class="muted">${device.id === "free_measurement"
      ? "What do you want to measure?"
      : `How do you want to measure ${device.label.toLowerCase()}?`}</p>
    <button type="button" @click=${onBack}>Change device</button>
    <div class="type-grid">
      ${routes.map((route) => html`<button type="button" class="type-card route-card" @click=${() => onSelect(route.id)}>
        <span class="type-label">${route.label}</span>
        <span class="type-desc">${route.description}</span>
      </button>`)}
    </div>
  `;
}

/** Restate the chosen device and route while showing the measurement form. */
export function renderSelectionChip(device: DeviceChoice, route: MeasurementRoute, onChangeDevice: () => void, onChangeRoute: () => void, multipleRoutes: boolean) {
  return html`
    <div class="type-chip">
      <span class="device-icon" aria-hidden="true">${deviceIcon(device.id)}</span>
      <span class="chip-body">
        <strong>${device.label}</strong>
        <span class="type-desc">${route.label}</span>
      </span>
      <span class="selection-actions">
        ${multipleRoutes ? html`<button type="button" @click=${onChangeRoute}>Change method</button>` : ""}
        <button type="button" @click=${onChangeDevice}>Change device</button>
      </span>
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
      <span class="power-meter-icon" aria-hidden="true">${deviceIcon("power_meter")}</span>
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
