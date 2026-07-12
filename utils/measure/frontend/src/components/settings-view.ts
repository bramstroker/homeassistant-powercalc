import { LitElement, css, html, nothing } from "lit";
import { createRef, ref } from "lit/directives/ref.js";
import type { AppSettings, EntityDescriptor, PowerMeterTestResult } from "../types";
import { sharedStyles } from "../styles";

export class SettingsView extends LitElement {
  static readonly properties = {
    powers: { attribute: false },
    settings: { attribute: false },
    busy: { type: Boolean },
    testing: { type: Boolean },
    testResult: { attribute: false },
    errorMessage: { type: String },
    meter: { state: true },
  };

  powers: EntityDescriptor[] = [];
  settings?: AppSettings;
  meter?: AppSettings["power_meter"];
  busy = false;
  testing = false;
  testResult?: PowerMeterTestResult;
  errorMessage = "";
  private readonly form = createRef<HTMLFormElement>();

  static readonly styles = [sharedStyles, css`
    form { display: grid; gap: 1rem; margin-top: 1rem; }
    label { display: grid; gap: 0.4rem; }
    label > span { color: var(--muted); font-size: 0.82rem; font-weight: 650; }
    input, select {
      width: 100%; min-height: 44px; border: 1px solid var(--line); border-radius: 9px;
      padding: 0.65rem 0.75rem; background: var(--field); color: var(--ink);
    }
    .context { display: flex; justify-content: space-between; gap: 1rem; align-items: baseline; }
    .test-row { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }
    .test-row button { min-height: 40px; }
    .test-result { font-size: 0.85rem; font-weight: 650; }
    .test-result.ok { color: var(--good); }
    .test-result.fail { color: var(--danger); }
  `];

  render() {
    const selected = this.settings?.default_power_entity_id ?? "";
    const powerMeter = this.meter ?? this.settings?.power_meter ?? "hass";
    return html`
      <section class="panel" aria-labelledby="settings-title">
        <div class="context">
          <div>
            <p class="eyebrow">Settings</p>
            <h2 id="settings-title">Measurement defaults</h2>
          </div>
        </div>
        <p class="muted">Defaults are applied to every new measurement. You can still change them per session.</p>
        <form ${ref(this.form)} @submit=${this.submit}>
          <label>
            <span>Default measurement device</span>
            <input name="default_measure_device" .value=${this.settings?.default_measure_device ?? ""} autocomplete="off" placeholder="e.g. Shelly Plug S" />
          </label>
          <label>
            <span>Power meter backend</span>
            <select name="power_meter" @change=${this.powerMeterChanged}>
              <option value="hass" ?selected=${powerMeter === "hass"}>Home Assistant sensor</option>
              <option value="shelly" ?selected=${powerMeter === "shelly"}>Shelly plug</option>
              <option value="dummy" ?selected=${powerMeter === "dummy"}>Dummy meter</option>
            </select>
          </label>
          ${powerMeter === "shelly" ? html`<label><span>Shelly IP address</span><input name="shelly_ip" .value=${this.settings?.shelly_ip ?? ""} required autocomplete="off" placeholder="192.168.1.50" /></label>` : nothing}
          ${powerMeter === "hass" ? html`<label>
            <span>Default power sensor</span>
            <select name="default_power_entity_id">
              <option value="">No default</option>
              ${this.powers.map((entity) => html`<option value=${entity.entity_id} ?selected=${entity.entity_id === selected}>${entity.name} · ${entity.entity_id}</option>`)}
            </select>
          </label>` : nothing}
          ${powerMeter === "dummy" ? nothing : html`
            <div class="test-row">
              <button type="button" @click=${this.test} ?disabled=${this.testing || this.busy}>${this.testing ? "Testing…" : "Test connection"}</button>
              ${this.renderTestResult()}
            </div>`}
          ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}</p>` : nothing}
          <div class="actions">
            <button type="button" @click=${() => this.emit("back")}>Back</button>
            <button class="primary" type="submit" ?disabled=${this.busy}>${this.busy ? "Saving…" : "Save settings"}</button>
          </div>
        </form>
      </section>
    `;
  }

  private renderTestResult() {
    if (!this.testResult) return nothing;
    if (this.testResult.success) {
      return html`<span class="test-result ok" role="status">✓ Reading ${this.testResult.power ?? "—"} W</span>`;
    }
    return html`<span class="test-result fail" role="alert">✕ ${this.testResult.message ?? "No reading"}</span>`;
  }

  private collect(): AppSettings | null {
    const element = this.form.value;
    if (!element) return null;
    const data = new FormData(element);
    const value = data.get("default_power_entity_id");
    const powerMeter = String(data.get("power_meter") ?? "hass") as AppSettings["power_meter"];
    const shellyIp = data.get("shelly_ip");
    const measureDevice = data.get("default_measure_device");
    return {
      default_power_entity_id: typeof value === "string" && value ? value : null,
      default_measure_device: typeof measureDevice === "string" && measureDevice.trim() ? measureDevice.trim() : null,
      power_meter: powerMeter,
      shelly_ip: powerMeter === "shelly" && typeof shellyIp === "string" ? shellyIp.trim() || null : null,
    };
  }

  private submit(event: SubmitEvent): void {
    event.preventDefault();
    const settings = this.collect();
    if (!settings) return;
    this.dispatchEvent(new CustomEvent<AppSettings>("save", { detail: settings, bubbles: true, composed: true }));
  }

  private test(): void {
    const settings = this.collect();
    if (!settings) return;
    this.testResult = undefined;
    this.dispatchEvent(new CustomEvent<AppSettings>("test", { detail: settings, bubbles: true, composed: true }));
  }

  private powerMeterChanged(event: Event): void {
    this.testResult = undefined;
    // Keep the choice in local state so an app-shell re-render can't clobber the
    // in-progress form (which would reset the meter type and typed Shelly IP).
    this.meter = (event.currentTarget as HTMLSelectElement).value as AppSettings["power_meter"];
  }

  private emit(name: "back"): void {
    this.dispatchEvent(new CustomEvent(name, { bubbles: true, composed: true }));
  }
}

customElements.define("measure-settings-view", SettingsView);
