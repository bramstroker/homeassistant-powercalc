import { LitElement, css, html, nothing } from "lit";
import type { Capabilities, EntityDescriptor, LutMode, MeasurementRequest } from "../types";
import { sharedStyles } from "../styles";

const fallbackDefaults = {
  sleep_time: 2,
  sample_count: 1,
  brightness_step: 5,
  hue_step: 10,
  saturation_step: 10,
  color_temp_step: 5,
};

export class SetupView extends LitElement {
  static readonly properties = {
    capabilities: { attribute: false },
    lights: { attribute: false },
    powers: { attribute: false },
    voltages: { attribute: false },
    initialRequest: { attribute: false },
    defaultPowerEntityId: { type: String },
    busy: { type: Boolean },
    errorMessage: { type: String },
    selectedLightId: { state: true },
  };

  capabilities?: Capabilities;
  lights: EntityDescriptor[] = [];
  powers: EntityDescriptor[] = [];
  voltages: EntityDescriptor[] = [];
  initialRequest?: MeasurementRequest;
  defaultPowerEntityId = "";
  busy = false;
  errorMessage = "";
  selectedLightId = "";

  static readonly styles = [sharedStyles, css`
    form { display: grid; gap: 1rem; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
    label, fieldset { display: grid; gap: 0.4rem; }
    label > span, legend { color: var(--muted); font-size: 0.82rem; font-weight: 650; }
    input, select {
      width: 100%; min-height: 44px; border: 1px solid var(--line); border-radius: 9px;
      padding: 0.65rem 0.75rem; background: var(--field); color: var(--ink);
    }
    fieldset { border: 0; padding: 0; margin: 0; }
    .checks { display: flex; flex-wrap: wrap; gap: 0.6rem; }
    .check { display: flex; grid-template-columns: none; align-items: center; gap: 0.5rem; min-height: 42px; padding: 0 0.75rem; border: 1px solid var(--line); border-radius: 999px; color: var(--ink); }
    .check input { min-height: auto; width: auto; accent-color: var(--signal); }
    details { border-top: 1px solid var(--line); padding-top: 1rem; }
    summary { width: fit-content; color: var(--signal-strong); cursor: pointer; font-weight: 700; }
    details .grid { margin-top: 1rem; }
    .context { display: flex; justify-content: space-between; gap: 1rem; align-items: baseline; }
    .context p { margin-bottom: 0; }
    @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } .context { display: block; } }
  `];

  render() {
    const defaults = this.capabilities?.defaults ?? fallbackDefaults;
    const request = this.initialRequest;
    const modes = this.availableModes(request);
    const selectedModes = request?.modes.length ? request.modes : modes;
    return html`
      <section class="panel" aria-labelledby="setup-title">
        <div class="context">
          <div>
            <p class="eyebrow">01 / Setup</p>
            <h2 id="setup-title">Configure the measurement</h2>
          </div>
        </div>
        <form @submit=${this.submit}>
          <div class="grid">
            ${this.textField("model_id", "Model ID", request?.model_id, "e.g. LWA017", true)}
            ${this.textField("product_name", "Full product name", request?.product_name, "e.g. Hue White Ambiance", true)}
            ${this.textField("measure_device", "Measurement device", request?.measure_device, "e.g. Shelly Plug S", true)}
            ${this.numberField("multiple_light_count", "Number of lights", request?.multiple_light_count ?? 1, 1, 100)}
          </div>

          <div class="grid">
            ${this.entitySelect("light_entity_id", "Light", this.lights, request?.light_entity_id, true)}
            ${this.entitySelect("power_entity_id", "Power sensor", this.powers, request?.power_entity_id ?? this.defaultPowerEntityId, true)}
          </div>
          ${this.entitySelect("voltage_entity_id", "Voltage sensor (optional)", this.voltages, request?.voltage_entity_id ?? "", false)}

          <fieldset>
            <legend>Lookup-table modes</legend>
            <div class="checks">
              ${modes.map((mode) => html`
                <label class="check">
                  <input type="checkbox" name="modes" value=${mode} .checked=${selectedModes.includes(mode)} />
                  ${this.modeLabel(mode)}
                </label>
              `)}
            </div>
          </fieldset>

          <div class="checks">
            ${this.boolField("generate_model", "Generate model.json", request?.generate_model ?? true)}
            ${this.boolField("gzip", "Compress CSV files", request?.gzip ?? true)}
          </div>

          <details>
            <summary>Advanced timing & quality</summary>
            <div class="grid">
              <label><span>Previous measurement</span><select name="resume_policy">
                <option value="new" ?selected=${(request?.resume_policy ?? "new") === "new"}>Keep it and start a new session</option>
                <option value="overwrite" ?selected=${request?.resume_policy === "overwrite"}>Delete it and start over</option>
              </select></label>
              ${this.numberField("sleep_time", "Settle time (seconds)", request?.sleep_time ?? defaults.sleep_time, 0, 120, "0.1")}
              ${this.numberField("sample_count", "Samples per step", request?.sample_count ?? defaults.sample_count, 1, 100)}
              ${this.numberField("brightness_step", "Brightness step", request?.brightness_step ?? defaults.brightness_step, 1, 100)}
              ${this.numberField("color_temp_step", "Color temperature step", request?.color_temp_step ?? defaults.color_temp_step, 1, 100)}
              ${this.numberField("hue_step", "Hue step", request?.hue_step ?? defaults.hue_step, 1, 360)}
              ${this.numberField("saturation_step", "Saturation step", request?.saturation_step ?? defaults.saturation_step, 1, 100)}
            </div>
          </details>

          ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}</p>` : nothing}
          <div class="actions"><button class="primary" type="submit" ?disabled=${this.busy}>${this.busy ? "Checking…" : "Review preflight"}</button></div>
        </form>
      </section>
    `;
  }

  private textField(name: string, label: string, value = "", placeholder = "", required = false) {
    return html`<label><span>${label}</span><input name=${name} .value=${value} placeholder=${placeholder} ?required=${required} autocomplete="off" /></label>`;
  }

  private numberField(name: string, label: string, value: number, min: number, max: number, step = "1") {
    return html`<label><span>${label}</span><input type="number" name=${name} .value=${String(value)} min=${min} max=${max} step=${step} required /></label>`;
  }

  private entitySelect(name: string, label: string, entities: EntityDescriptor[], selected = "", required = false) {
    return html`
      <label><span>${label}</span><select name=${name} ?required=${required} @change=${name === "light_entity_id" ? this.lightChanged : null}>
        <option value="">${required ? "Select an entity" : "None"}</option>
        ${entities.map((entity) => html`<option value=${entity.entity_id} ?selected=${entity.entity_id === selected}>${entity.name} · ${entity.entity_id}</option>`)}
      </select></label>
    `;
  }

  private boolField(name: string, label: string, checked: boolean) {
    return html`<label class="check"><input type="checkbox" name=${name} .checked=${checked} />${label}</label>`;
  }

  private modeLabel(mode: LutMode): string {
    return { brightness: "Brightness", color_temp: "Color temperature", hs: "Hue & saturation", effect: "Effect" }[mode];
  }

  private availableModes(request?: MeasurementRequest): LutMode[] {
    const supported = this.capabilities?.modes ?? ["brightness", "color_temp", "hs"];
    const lightId = this.selectedLightId || request?.light_entity_id;
    const entityModes = this.lights.find((entity) => entity.entity_id === lightId)?.supported_modes;
    return entityModes?.length ? supported.filter((mode) => entityModes.includes(mode)) : supported;
  }

  private lightChanged(event: Event): void {
    this.selectedLightId = (event.currentTarget as HTMLSelectElement).value;
  }

  private submit(event: SubmitEvent): void {
    event.preventDefault();
    const data = new FormData(event.currentTarget as HTMLFormElement);
    const modes = data.getAll("modes") as LutMode[];
    if (modes.length === 0) {
      this.errorMessage = "Select at least one lookup-table mode.";
      return;
    }
    const text = (name: string): string => {
      const value = data.get(name);
      return typeof value === "string" ? value : "";
    };
    const number = (name: string) => Number(text(name));
    const request: MeasurementRequest = {
      model_id: text("model_id").trim(),
      product_name: text("product_name").trim(),
      measure_device: text("measure_device").trim(),
      light_entity_id: text("light_entity_id"),
      power_entity_id: text("power_entity_id"),
      voltage_entity_id: text("voltage_entity_id") || null,
      modes,
      generate_model: data.has("generate_model"),
      gzip: data.has("gzip"),
      multiple_light_count: number("multiple_light_count"),
      sleep_time: number("sleep_time"),
      sample_count: number("sample_count"),
      brightness_step: number("brightness_step"),
      hue_step: number("hue_step"),
      saturation_step: number("saturation_step"),
      color_temp_step: number("color_temp_step"),
      resume_policy: (text("resume_policy") || "new") as MeasurementRequest["resume_policy"],
    };
    this.dispatchEvent(new CustomEvent("preflight", { detail: request, bubbles: true, composed: true }));
  }
}

customElements.define("measure-setup-view", SetupView);
