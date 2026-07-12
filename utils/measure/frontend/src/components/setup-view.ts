import { LitElement, css, html, nothing } from "lit";
import type {
  AppSettings,
  Capabilities,
  EntityDescriptor,
  LutMode,
  MeasureDefinition,
  MeasureType,
  MeasurementRequest,
  MeasurementRunRequest,
} from "../types";
import { sharedStyles } from "../styles";

const fallbackDefaults = {
  sleep_time: 2,
  sample_count: 1,
  brightness_step: 5,
  hue_step: 10,
  saturation_step: 10,
  color_temp_step: 5,
};

const LIGHT_TYPE: MeasureType = "Light bulb(s)";

/** Emoji glyph per measurement type — keeps the picker recognisable without shipping icon assets. */
const TYPE_ICONS: Record<MeasureType, string> = {
  "Light bulb(s)": "💡",
  "Smart speaker": "🔊",
  Recorder: "⏺",
  Average: "📊",
  "Charging device": "🔋",
  Fan: "🌀",
};

export class SetupView extends LitElement {
  static readonly properties = {
    capabilities: { attribute: false },
    definitions: { attribute: false },
    lights: { attribute: false },
    powers: { attribute: false },
    voltages: { attribute: false },
    deviceEntities: { attribute: false },
    initialRequest: { attribute: false },
    initialRunRequest: { attribute: false },
    initialType: { attribute: false },
    defaultPowerEntityId: { type: String },
    defaultMeasureDevice: { type: String },
    powerMeter: { type: String },
    busy: { type: Boolean },
    errorMessage: { type: String },
    selectedType: { state: true },
    selectedLightId: { state: true },
    selectedPowerId: { state: true },
  };

  capabilities?: Capabilities;
  definitions: MeasureDefinition[] = [];
  lights: EntityDescriptor[] = [];
  powers: EntityDescriptor[] = [];
  voltages: EntityDescriptor[] = [];
  deviceEntities: Record<string, EntityDescriptor[]> = {};
  initialRequest?: MeasurementRequest;
  initialRunRequest?: MeasurementRunRequest;
  initialType?: MeasureType;
  defaultPowerEntityId = "";
  defaultMeasureDevice = "";
  powerMeter: AppSettings["power_meter"] = "hass";
  busy = false;
  errorMessage = "";
  selectedType?: MeasureType;
  selectedLightId = "";
  selectedPowerId = "";

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
    fieldset.section { border: 1px solid var(--line); border-radius: 12px; padding: 1rem 1.1rem 1.2rem; margin: 0; display: grid; gap: 1rem; }
    fieldset.section > legend { padding: 0 0.4rem; color: var(--signal-strong); font-size: 0.85rem; font-weight: 700; }
    .checks { display: flex; flex-wrap: wrap; gap: 0.6rem; }
    .check { display: flex; grid-template-columns: none; align-items: center; gap: 0.5rem; min-height: 42px; padding: 0 0.75rem; border: 1px solid var(--line); border-radius: 999px; color: var(--ink); }
    .check input { min-height: auto; width: auto; accent-color: var(--signal); }
    details { border-top: 1px solid var(--line); padding-top: 1rem; }
    summary { width: fit-content; color: var(--signal-strong); cursor: pointer; font-weight: 700; }
    details .grid { margin-top: 1rem; }
    .context { display: flex; justify-content: space-between; gap: 1rem; align-items: baseline; }
    .context p { margin-bottom: 0; }

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

    @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } .context { display: block; } .type-grid { grid-template-columns: 1fr; } }
  `];

  willUpdate(changed: Map<string, unknown>): void {
    // Restore the previously chosen type when returning from the review step.
    if (changed.has("initialType") && this.initialType && this.selectedType === undefined) {
      this.selectedType = this.initialType;
    }
  }

  render() {
    return html`
      <section class="panel" aria-labelledby="setup-title">
        <div class="context">
          <div>
            <p class="eyebrow">01 / Setup</p>
            <h2 id="setup-title">Configure the measurement</h2>
          </div>
        </div>
        ${this.selectedType ? this.renderChip(this.selectedType) : this.renderPicker()}
        ${this.selectedType === LIGHT_TYPE ? this.renderLightForm() : nothing}
        ${this.selectedType && this.selectedType !== LIGHT_TYPE ? this.renderGenericForm(this.selectedType) : nothing}
      </section>
    `;
  }

  private renderPicker() {
    if (!this.definitions.length) {
      return html`<p class="muted">Loading measurement types…</p>`;
    }
    return html`
      <p class="muted">What do you want to measure?</p>
      <div class="type-grid" role="list">
        ${this.definitions.map((definition) => html`
          <button type="button" class="type-card" role="listitem" @click=${() => this.selectType(definition.measure_type)}>
            <span class="type-icon" aria-hidden="true">${TYPE_ICONS[definition.measure_type] ?? "•"}</span>
            <span class="type-label">${definition.label}</span>
            <span class="type-desc">${definition.description}</span>
          </button>
        `)}
      </div>
    `;
  }

  private renderChip(type: MeasureType) {
    const definition = this.definition(type);
    return html`
      <div class="type-chip">
        <span class="type-icon" aria-hidden="true">${TYPE_ICONS[type] ?? "•"}</span>
        <span class="chip-body">
          <strong>${definition?.label ?? type}</strong>
          ${definition ? html`<span class="type-desc">${definition.description}</span>` : nothing}
        </span>
        <button type="button" @click=${this.changeType}>Change</button>
      </div>
    `;
  }

  private renderLightForm() {
    const defaults = this.capabilities?.defaults ?? fallbackDefaults;
    const request = this.initialRequest;
    const modes = this.availableModes(request);
    const selectedModes = request?.modes.length ? request.modes : modes;
    return html`
      <form @submit=${this.submitLight}>
        <fieldset class="section">
          <legend>Power measurement</legend>
          <div class="grid">
            ${this.textField("measure_device", "Measurement device", request?.measure_device ?? this.defaultMeasureDevice, "e.g. Shelly Plug S", true)}
            ${this.powerMeter === "hass" ? this.entitySelect("power_entity_id", "Power sensor", this.powers, this.powerEntityId(request), true) : nothing}
          </div>
          ${this.powerMeter === "hass" ? html`<div class="grid">
            ${this.entitySelect("voltage_entity_id", "Voltage sensor (optional)", this.voltages, this.voltageEntityId(request), false)}
          </div>` : this.powerMeterNote()}
        </fieldset>

        <fieldset class="section">
          <legend>Light profile</legend>
          <div class="grid">
            ${this.textField("model_id", "Model ID", request?.model_id, "e.g. LWA017", true)}
            ${this.textField("product_name", "Full product name", request?.product_name, "e.g. Hue White Ambiance", true)}
            ${this.entitySelect("light_entity_id", "Light", this.lights, request?.light_entity_id, true)}
            ${this.numberField("multiple_light_count", "Number of lights", request?.multiple_light_count ?? 1, 1, 100)}
          </div>

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
        </fieldset>

        ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}</p>` : nothing}
        <div class="actions"><button class="primary" type="submit" ?disabled=${this.busy}>${this.busy ? "Checking…" : "Review preflight"}</button></div>
      </form>
    `;
  }

  private renderGenericForm(type: MeasureType) {
    const definition = this.definition(type);
    if (!definition) return nothing;
    const run = this.initialRunRequest;
    const fields = definition.fields.filter((field) => field.name !== "powermeter_entity_id");
    const power = run?.answers?.powermeter_entity_id?.toString() ?? this.defaultPowerEntityId;
    return html`
      <form @submit=${this.submitGeneric}>
        <fieldset class="section">
          <legend>Power measurement</legend>
          <div class="grid">
            ${definition.supports_profile ? this.textField("measure_device", "Measurement device", run?.measure_device ?? this.defaultMeasureDevice, "e.g. Shelly Plug S", true) : nothing}
            ${this.powerMeter === "hass" ? this.entitySelect("power_entity_id", "Power sensor", this.powers, power, true) : nothing}
          </div>
          ${this.powerMeter === "hass" ? nothing : this.powerMeterNote()}
        </fieldset>

        <fieldset class="section">
          <legend>${definition.label}</legend>
          ${definition.supports_profile ? html`<div class="grid">
            ${this.textField("model_id", "Model ID", run?.model_id ?? "", "e.g. WSP002", true)}
            ${this.textField("product_name", "Full product name", run?.product_name ?? "", definition.label, true)}
          </div>` : nothing}
          <div class="grid">${fields.map((field) => this.genericField(field, run))}</div>
        </fieldset>

        ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}</p>` : nothing}
        <div class="actions"><button class="primary" type="submit" ?disabled=${this.busy}>${this.busy ? "Checking…" : "Review preflight"}</button></div>
      </form>
    `;
  }

  private powerMeterNote() {
    const label = this.powerMeter === "dummy" ? "dummy power meter" : "Shelly power meter";
    return html`<p class="muted">Power readings come from the configured ${label}. Change this under Settings.</p>`;
  }

  private textField(name: string, label: string, value = "", placeholder = "", required = false) {
    return html`<label><span>${label}</span><input name=${name} .value=${value} placeholder=${placeholder} ?required=${required} autocomplete="off" /></label>`;
  }

  private numberField(name: string, label: string, value: number, min: number, max: number, step = "1") {
    return html`<label><span>${label}</span><input type="number" name=${name} .value=${String(value)} min=${min} max=${max} step=${step} required /></label>`;
  }

  private entitySelect(name: string, label: string, entities: EntityDescriptor[], selected = "", required = false) {
    return html`
      <label><span>${label}</span><select name=${name} ?required=${required} @change=${name === "light_entity_id" ? this.lightChanged : name === "power_entity_id" ? this.powerChanged : null}>
        <option value="">${required ? "Select an entity" : "None"}</option>
        ${entities.map((entity) => html`<option value=${entity.entity_id} ?selected=${entity.entity_id === selected}>${entity.name} · ${entity.entity_id}</option>`)}
      </select></label>
    `;
  }

  private genericField(field: MeasureDefinition["fields"][number], run?: MeasurementRunRequest) {
    const stored = run?.answers?.[field.name];
    if (field.control === "boolean") {
      return html`<label class="check"><input type="checkbox" name=${field.name} .checked=${Boolean(stored ?? field.default)} />${field.label}</label>`;
    }
    if (field.control === "entity") {
      const value = (stored ?? field.default ?? "").toString();
      const entities = (field.entity_domain && this.deviceEntities[field.entity_domain]) || [];
      if (entities.length) {
        return this.entitySelect(field.name, field.label, entities, value, field.required);
      }
      // No matching entities were discovered — fall back to manual entry.
      return html`<label><span>${field.label}${field.entity_domain ? ` (${field.entity_domain})` : ""}</span><input name=${field.name} .value=${value} ?required=${field.required} placeholder=${field.entity_domain ? `${field.entity_domain}.example` : ""} autocomplete="off" /></label>`;
    }
    if (field.control === "select") {
      const value = (stored ?? field.default ?? "").toString();
      return html`<label><span>${field.label}</span><select name=${field.name} ?required=${field.required}>
        ${field.options.map((option) => html`<option value=${option.value} ?selected=${option.value === value}>${option.label}</option>`)}
      </select></label>`;
    }
    const type = field.control === "number" ? "number" : "text";
    const value = (stored ?? field.default ?? "").toString();
    return html`<label><span>${field.label}${field.entity_domain ? ` (${field.entity_domain})` : ""}</span><input type=${type} name=${field.name} .value=${value} ?required=${field.required} autocomplete="off" /></label>`;
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

  private selectType(type: MeasureType): void {
    this.errorMessage = "";
    this.selectedType = type;
  }

  private changeType(): void {
    this.errorMessage = "";
    this.selectedType = undefined;
  }

  private lightChanged(event: Event): void {
    this.selectedLightId = (event.currentTarget as HTMLSelectElement).value;
  }

  private powerChanged(event: Event): void {
    this.selectedPowerId = (event.currentTarget as HTMLSelectElement).value;
  }

  private definition(type: MeasureType): MeasureDefinition | undefined {
    return this.definitions.find((item) => item.measure_type === type);
  }

  private powerEntityId(request?: MeasurementRequest): string {
    return this.selectedPowerId || request?.power_entity_id || this.defaultPowerEntityId;
  }

  private voltageEntityId(request?: MeasurementRequest): string {
    if (request?.voltage_entity_id) {
      return request.voltage_entity_id;
    }
    return this.matchingVoltageEntityId(this.powerEntityId(request));
  }

  private matchingVoltageEntityId(powerEntityId: string): string {
    const devicePrefix = powerEntityId.endsWith("_power") ? powerEntityId.slice(0, -"_power".length) : "";
    return this.voltages.find((entity) => entity.entity_id === `${devicePrefix}_voltage`)?.entity_id ?? "";
  }

  private submitLight(event: SubmitEvent): void {
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
      generate_model: true,
      gzip: true,
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

  private submitGeneric(event: SubmitEvent): void {
    event.preventDefault();
    const definition = this.selectedType ? this.definition(this.selectedType) : undefined;
    if (!definition) return;
    const form = new FormData(event.currentTarget as HTMLFormElement);
    const answers: MeasurementRunRequest["answers"] = {};
    for (const field of definition.fields) {
      if (field.name === "powermeter_entity_id") continue;
      const value = form.get(field.name);
      answers[field.name] = field.control === "boolean" ? form.has(field.name) : field.control === "number" ? Number(value) : String(value ?? "");
    }
    answers.powermeter_entity_id = this.powerMeter === "hass" ? String(form.get("power_entity_id") ?? "") : "__managed__";
    const request: MeasurementRunRequest = {
      measure_type: definition.measure_type,
      model_id: String(form.get("model_id") ?? "measurement").trim() || "measurement",
      product_name: String(form.get("product_name") ?? definition.label).trim() || definition.label,
      measure_device: String(form.get("measure_device") ?? "").trim(),
      answers,
      generate_model: definition.supports_profile,
      sleep_time: 2,
      sample_count: 1,
      resume_policy: "new",
    };
    this.dispatchEvent(new CustomEvent("preflight-run", { detail: request, bubbles: true, composed: true }));
  }
}

customElements.define("measure-setup-view", SetupView);
