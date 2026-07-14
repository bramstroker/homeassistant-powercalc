import { LitElement, css, html, nothing } from "lit";
import type {
  AppSettings,
  Capabilities,
  EntityDescriptor,
  LutMode,
  LightMeasurementRequest,
  MeasureDefinition,
  MeasureType,
  MeasurementRequest,
  NonLightMeasurementRequest,
  PowerMeterSpec,
} from "../types";
import {
  buildNonLightRequest,
  canonicalFieldName,
  deviceFields,
  entityDomains,
  LIGHT_TYPE,
  measurementIcon,
  requestFieldValue,
} from "../measurement-kinds";
import { sharedStyles } from "../styles";

const FULL_PRODUCT_NAME_HINT = "Enter the complete marketed name, including the series and variant shown on the product or packaging.";

export class SetupView extends LitElement {
  static readonly properties = {
    capabilities: { attribute: false },
    definitions: { attribute: false },
    lights: { attribute: false },
    powers: { attribute: false },
    voltages: { attribute: false },
    deviceEntities: { attribute: false },
    deviceEntityErrors: { attribute: false },
    initialRequest: { attribute: false },
    initialType: { attribute: false },
    defaultPowerEntityId: { type: String },
    defaultMeasureDevice: { type: String },
    powerMeter: { type: String },
    shellyIp: { type: String },
    busy: { type: Boolean },
    errorMessage: { type: String },
    selectedType: { state: true },
    selectedLightId: { state: true },
    selectedPowerId: { state: true },
    selectedDeviceEntityId: { state: true },
    selectedChargingType: { state: true },
  };

  capabilities?: Capabilities;
  definitions: MeasureDefinition[] = [];
  lights: EntityDescriptor[] = [];
  powers: EntityDescriptor[] = [];
  voltages: EntityDescriptor[] = [];
  deviceEntities: Record<string, EntityDescriptor[]> = {};
  deviceEntityErrors: Record<string, string> = {};
  initialRequest?: MeasurementRequest;
  initialType?: MeasureType;
  defaultPowerEntityId = "";
  defaultMeasureDevice = "";
  powerMeter: AppSettings["power_meter"] = "hass";
  shellyIp = "";
  busy = false;
  errorMessage = "";
  selectedType?: MeasureType;
  selectedLightId = "";
  selectedPowerId = "";
  selectedDeviceEntityId = "";
  selectedChargingType = "";

  static readonly styles = [sharedStyles, css`
    form { display: grid; gap: 1rem; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
    .profile-grid { align-items: start; }
    label, fieldset { display: grid; gap: 0.4rem; }
    label > span, legend { color: var(--muted); font-size: 0.82rem; font-weight: 650; }
    .field-hint { color: var(--muted); font-size: 0.74rem; line-height: 1.4; }
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
    .advanced-heading { grid-column: 1 / -1; margin: 0.25rem 0 -0.25rem; color: var(--signal-strong); font-size: 0.76rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; }
    .effect-settings { grid-column: 1 / -1; }
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
            <span class="type-icon" aria-hidden="true">${measurementIcon(definition.measure_type)}</span>
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
        <span class="type-icon" aria-hidden="true">${measurementIcon(type)}</span>
        <span class="chip-body">
          <strong>${definition?.label ?? type}</strong>
          ${definition ? html`<span class="type-desc">${definition.description}</span>` : nothing}
        </span>
        <button type="button" @click=${this.changeType}>Change</button>
      </div>
    `;
  }

  private renderLightForm() {
    if (!this.capabilities) return html`<p class="muted">Loading measurement capabilities…</p>`;
    const defaults = this.capabilities.defaults;
    const request = this.initialRequest?.measure_type === LIGHT_TYPE ? this.initialRequest : undefined;
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
          <div class="grid profile-grid">
            ${this.entitySelect("light_entity_id", "Light", this.lights, request?.controller.type === "hass" ? request.controller.entity_id : "", true)}
            ${this.numberField("multiple_light_count", "Number of lights", request?.multiple_light_count ?? 1, 1, 100)}
            ${this.textField("model_id", "Model ID", this.modelId(request), "e.g. LWA017", true)}
            ${this.textField(
              "product_name",
              "Full product name",
              request?.product_name,
              "e.g. Philips Hue White Ambiance A60 E27",
              true,
              FULL_PRODUCT_NAME_HINT,
            )}
          </div>

          <fieldset>
            <legend>Lookup-table modes</legend>
            <div class="checks">
              ${modes.map((mode) => html`
                <label class="check">
                  <input type="checkbox" name="modes" value=${mode} .checked=${selectedModes.includes(mode)} @change=${this.modesChanged} />
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
              <p class="advanced-heading">Sampling</p>
              ${this.numberField("sleep_time", "Settle time (seconds)", request?.parameters.sleep_time ?? defaults.sleep_time, 0, 120, "0.1", "Wait after changing the light before reading power.")}
              ${this.numberField("sample_count", "Samples per point", request?.parameters.sample_count ?? defaults.sample_count, 1, 100, "1", "More samples reduce noise but increase measurement time.", false, this.sampleCountChanged)}
              ${this.numberField("sleep_time_sample", "Time between samples (seconds)", request?.parameters.sleep_time_sample ?? defaults.sleep_time_sample, 0, 120, "1", "Only used when taking more than one sample.", (request?.parameters.sample_count ?? defaults.sample_count) <= 1)}
              ${this.numberField("min_brightness", "Minimum brightness", request?.parameters.min_brightness ?? defaults.min_brightness, 1, 255, "1", "Increase this when the light does not turn on at its lowest level.")}
              ${this.numberField("sleep_initial", "Initial stabilization (seconds)", request?.parameters.sleep_initial ?? defaults.sleep_initial, 0, 3600)}
              ${this.numberField("sleep_standby", "Standby stabilization (seconds)", request?.parameters.sleep_standby ?? defaults.sleep_standby, 0, 3600)}
              <p class="advanced-heading">Profile resolution</p>
              ${this.numberField("brightness_step", "Brightness step (%)", request?.parameters.brightness_step ?? defaults.brightness_step, 1, 100)}
              ${this.numberField("color_temp_step", "Color temperature step (%)", request?.parameters.color_temp_step ?? defaults.color_temp_step, 1, 100)}
              ${this.numberField("hue_step", "Hue step (degrees)", request?.parameters.hue_step ?? defaults.hue_step, 1, 360)}
              ${this.numberField("saturation_step", "Saturation step (%)", request?.parameters.saturation_step ?? defaults.saturation_step, 1, 100)}
              <div class="grid effect-settings" ?hidden=${!selectedModes.includes("effect")}>
                <p class="advanced-heading">Effect mode</p>
                ${this.numberField("effect_bri_steps", "Effect brightness step", request?.parameters.effect_bri_steps ?? defaults.effect_bri_steps, 1, 255, "1", "Native brightness increment between long-running effect samples.", !selectedModes.includes("effect"))}
                ${this.numberField("measure_time_effect_min", "Minimum time per effect (seconds)", request?.parameters.measure_time_effect_min ?? defaults.measure_time_effect_min, 1, 3600, "1", "An effect can stop after this time once its average converges.", !selectedModes.includes("effect"))}
                ${this.numberField("measure_time_effect", "Maximum time per effect (seconds)", request?.parameters.measure_time_effect ?? defaults.measure_time_effect, 1, 3600, "1", "Upper time limit for every effect and brightness combination.", !selectedModes.includes("effect"))}
              </div>
            </div>
          </details>
        </fieldset>

        ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}</p>` : nothing}
        <div class="actions"><button class="primary" type="submit" ?disabled=${this.busy}>${this.busy ? "Checking setup…" : "Check setup"}</button></div>
      </form>
    `;
  }

  private renderGenericForm(type: MeasureType) {
    const definition = this.definition(type);
    if (!definition || !this.capabilities) return html`<p class="muted">Loading measurement capabilities…</p>`;
    const run = this.nonLightRequest();
    const fields = deviceFields(definition);
    const power = run?.power_meter.type === "hass" ? run.power_meter.entity_id : this.defaultPowerEntityId;
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
          <div class="grid profile-grid">
            ${fields.map((field) => this.genericField(field, run))}
            ${definition.supports_profile ? this.textField("model_id", "Model ID", this.modelId(run), "e.g. WSP002", true) : nothing}
            ${definition.supports_profile
              ? this.textField("product_name", "Full product name", run?.product_name ?? "", definition.label, true, FULL_PRODUCT_NAME_HINT)
              : nothing}
          </div>
        </fieldset>

        ${this.renderGenericTuning(type, run)}

        ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}</p>` : nothing}
        <div class="actions"><button class="primary" type="submit" ?disabled=${this.busy}>${this.busy ? "Checking setup…" : "Check setup"}</button></div>
      </form>
    `;
  }

  private powerMeterNote() {
    const label = this.powerMeter === "dummy" ? "dummy power meter" : "Shelly power meter";
    return html`<p class="muted">Power readings come from the configured ${label}. Change this under Settings.</p>`;
  }

  private renderGenericTuning(type: MeasureType, request?: NonLightMeasurementRequest) {
    if (!this.capabilities) return nothing;
    const defaults = this.capabilities.defaults;
    const supportsPointSamples = type === "charging" || type === "recorder";
    return html`<details>
      <summary>Advanced timing & quality</summary>
      <div class="grid">
        ${this.numberField("sleep_time", "Reading interval (seconds)", request?.parameters.sleep_time ?? defaults.sleep_time, 0, 120, "0.1", "Delay between repeated power readings and retries.")}
        ${supportsPointSamples
          ? this.numberField("sample_count", "Samples per reading", request?.parameters.sample_count ?? defaults.sample_count, 1, 100, "1", "More samples reduce noise but increase measurement time.", false, this.sampleCountChanged)
          : nothing}
        ${supportsPointSamples
          ? this.numberField("sleep_time_sample", "Time between samples (seconds)", request?.parameters.sleep_time_sample ?? defaults.sleep_time_sample, 0, 120, "1", "Only used when taking more than one sample.", (request?.parameters.sample_count ?? defaults.sample_count) <= 1)
          : nothing}
        ${type === "speaker"
          ? this.numberField("sleep_standby", "Standby stabilization (seconds)", request?.parameters.sleep_standby ?? defaults.sleep_standby, 0, 3600)
          : nothing}
      </div>
    </details>`;
  }

  private textField(name: string, label: string, value = "", placeholder = "", required = false, hint = "") {
    return html`<label>
      <span>${label}</span>
      <input name=${name} .value=${value} placeholder=${placeholder} ?required=${required} autocomplete="off" />
      ${hint ? html`<small class="field-hint">${hint}</small>` : nothing}
    </label>`;
  }

  private numberField(
    name: string,
    label: string,
    value: number,
    fallbackMin: number,
    fallbackMax: number,
    step = "1",
    hint = "",
    disabled = false,
    onInput: ((event: Event) => void) | null = null,
  ) {
    // Bounds come from the capabilities endpoint so the form cannot drift from
    // server-side validation; the literals only cover fields without server limits.
    const { min, max } = this.capabilities?.limits?.[name] ?? { min: fallbackMin, max: fallbackMax };
    return html`<label>
      <span>${label}</span>
      <input type="number" name=${name} .value=${String(value)} min=${min} max=${max} step=${step} required ?disabled=${disabled} @input=${onInput} />
      ${hint ? html`<small class="field-hint">${hint}</small>` : nothing}
    </label>`;
  }

  private entitySelect(name: string, label: string, entities: EntityDescriptor[], selected = "", required = false) {
    return html`
      <label><span>${label}</span><select name=${name} ?required=${required} @change=${this.entityChanged(name)}>
        <option value="">${required ? "Select an entity" : "None"}</option>
        ${entities.map((entity) => html`<option value=${entity.entity_id} ?selected=${entity.entity_id === selected}>${entity.name} · ${entity.entity_id}</option>`)}
      </select></label>
    `;
  }

  private genericField(field: MeasureDefinition["fields"][number], run?: NonLightMeasurementRequest) {
    if (!this.selectedType) return nothing;
    const name = canonicalFieldName(this.selectedType, field.name);
    const stored = run && requestFieldValue(run, name);
    if (field.control === "boolean") {
      return html`<label class="check"><input type="checkbox" name=${name} .checked=${Boolean(stored ?? field.default)} />${field.label}</label>`;
    }
    if (field.control === "entity") {
      const value = (stored ?? field.default ?? "").toString();
      const domains = name === "charging_entity_id" ? [this.chargingDomain(run)] : this.fieldDomains(field);
      const failed = domains.find((domain) => this.deviceEntityErrors[domain]);
      if (failed) {
        return html`<div class="notice error" role="alert">Could not load ${field.label.toLowerCase()} entities: ${this.deviceEntityErrors[failed]}</div>`;
      }
      const entities = domains.flatMap((domain) => this.deviceEntities[domain] ?? []);
      return this.entitySelect(name, field.label, entities, value, field.required);
    }
    if (field.control === "select") {
      const value = (stored ?? field.default ?? "").toString();
      return html`<label><span>${field.label}</span><select name=${name} ?required=${field.required} @change=${name === "charging_device_type" ? this.chargingTypeChanged : null}>
        ${field.options.map((option) => html`<option value=${option.value} ?selected=${option.value === value}>${option.label}</option>`)}
      </select></label>`;
    }
    const type = field.control === "number" ? "number" : "text";
    const value = (stored ?? field.default ?? "").toString();
    return html`<label><span>${field.label}</span><input
      type=${type}
      name=${name}
      .value=${value}
      min=${field.minimum ?? nothing}
      max=${field.maximum ?? nothing}
      ?required=${field.required}
      autocomplete="off"
    /></label>`;
  }

  private fieldDomains(field: MeasureDefinition["fields"][number]): string[] {
    if (field.entity_domains?.length) return field.entity_domains;
    return field.entity_domain ? [field.entity_domain] : [];
  }

  private modeLabel(mode: LutMode): string {
    return { brightness: "Brightness", color_temp: "Color temperature", hs: "Hue & saturation", effect: "Effect" }[mode];
  }

  private modesChanged(): void {
    const effectEnabled = Boolean(this.shadowRoot?.querySelector<HTMLInputElement>('input[name="modes"][value="effect"]')?.checked);
    const settings = this.shadowRoot?.querySelector<HTMLElement>(".effect-settings");
    if (!settings) return;
    settings.hidden = !effectEnabled;
    settings.querySelectorAll<HTMLInputElement>("input").forEach((input) => {
      input.disabled = !effectEnabled;
    });
  }

  private sampleCountChanged(event: Event): void {
    const count = Number((event.currentTarget as HTMLInputElement).value);
    const interval = this.shadowRoot?.querySelector<HTMLInputElement>('input[name="sleep_time_sample"]');
    if (interval) interval.disabled = count <= 1;
  }

  private availableModes(request?: LightMeasurementRequest): LutMode[] {
    const supported = this.capabilities?.modes ?? [];
    const lightId = this.selectedLightId || (request?.controller.type === "hass" ? request.controller.entity_id : "");
    const entityModes = this.lights.find((entity) => entity.entity_id === lightId)?.supported_modes;
    return entityModes?.length ? supported.filter((mode) => entityModes.includes(mode)) : supported;
  }

  private nonLightRequest(): NonLightMeasurementRequest | undefined {
    const request = this.initialRequest;
    return request && request.measure_type !== LIGHT_TYPE ? request as NonLightMeasurementRequest : undefined;
  }

  private selectType(type: MeasureType): void {
    this.errorMessage = "";
    this.selectedType = type;
    this.dispatchEvent(new CustomEvent("measure-type-selected", { detail: type, bubbles: true, composed: true }));
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

  private deviceChanged(event: Event): void {
    this.selectedDeviceEntityId = (event.currentTarget as HTMLSelectElement).value;
  }

  private entityChanged(name: string): ((event: Event) => void) | null {
    if (name === "light_entity_id") return this.lightChanged;
    if (name === "power_entity_id") return this.powerChanged;
    if (name === "voltage_entity_id") return null;
    return this.deviceChanged;
  }

  private chargingTypeChanged(event: Event): void {
    this.selectedChargingType = (event.currentTarget as HTMLSelectElement).value;
    const definition = this.definition("charging");
    if (definition) this.dispatchEvent(new CustomEvent("entity-domains-requested", { detail: entityDomains(definition), bubbles: true, composed: true }));
  }

  private chargingDomain(run?: NonLightMeasurementRequest): string {
    const chargingType = this.selectedChargingType
      || (run?.measure_type === "charging" ? run.charging_device_type : "vacuum_robot");
    return chargingType === "lawn_mower_robot" ? "lawn_mower" : "vacuum";
  }

  private definition(type: MeasureType): MeasureDefinition | undefined {
    return this.definitions.find((item) => item.measure_type === type);
  }

  private powerEntityId(request?: LightMeasurementRequest): string {
    const requestEntityId = request?.power_meter.type === "hass" ? request.power_meter.entity_id : "";
    return this.selectedPowerId || requestEntityId || this.defaultPowerEntityId;
  }

  private voltageEntityId(request?: LightMeasurementRequest): string {
    if (request?.power_meter.type === "hass" && request.power_meter.voltage_entity_id) {
      return request.power_meter.voltage_entity_id;
    }
    return this.matchingVoltageEntityId(this.powerEntityId(request));
  }

  private matchingVoltageEntityId(powerEntityId: string): string {
    const deviceId = this.powers.find((entity) => entity.entity_id === powerEntityId)?.device_id;
    if (!deviceId) return "";
    return this.voltages.find((entity) => entity.device_id === deviceId)?.entity_id ?? "";
  }

  private modelId(request?: MeasurementRequest): string {
    if (request?.model_id) return request.model_id;
    const requestEntityId = request && "controller" in request && request.controller.type === "hass" ? request.controller.entity_id : "";
    const entityId = this.selectedType === LIGHT_TYPE ? this.selectedLightId || requestEntityId : this.selectedDeviceEntityId || requestEntityId;
    const entities = [...this.lights, ...Object.values(this.deviceEntities).flat()];
    return entities.find((entity) => entity.entity_id === entityId)?.model_id ?? "";
  }

  private submitLight(event: SubmitEvent): void {
    event.preventDefault();
    if (!this.capabilities) return;
    const defaults = this.capabilities.defaults;
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
    const numberOrDefault = (name: keyof typeof defaults): number => {
      const value = text(name);
      return value === "" ? defaults[name] : Number(value);
    };
    const request: LightMeasurementRequest = {
      measure_type: LIGHT_TYPE,
      model_id: text("model_id").trim(),
      product_name: text("product_name").trim(),
      measure_device: text("measure_device").trim(),
      controller: { type: "hass", entity_id: text("light_entity_id") },
      power_meter: this.powerMeterSpec(text("power_entity_id"), text("voltage_entity_id") || null),
      modes,
      generate_model: true,
      gzip: true,
      multiple_light_count: number("multiple_light_count"),
      parameters: {
        sleep_time: numberOrDefault("sleep_time"),
        sample_count: numberOrDefault("sample_count"),
        sleep_time_sample: numberOrDefault("sleep_time_sample"),
        max_retries: defaults.max_retries,
        max_nudges: defaults.max_nudges,
        brightness_step: numberOrDefault("brightness_step"),
        hue_step: numberOrDefault("hue_step"),
        saturation_step: numberOrDefault("saturation_step"),
        color_temp_step: numberOrDefault("color_temp_step"),
        min_brightness: numberOrDefault("min_brightness"),
        sleep_initial: numberOrDefault("sleep_initial"),
        sleep_standby: numberOrDefault("sleep_standby"),
        effect_bri_steps: numberOrDefault("effect_bri_steps"),
        measure_time_effect: numberOrDefault("measure_time_effect"),
        measure_time_effect_min: numberOrDefault("measure_time_effect_min"),
      },
      resume_policy: (text("resume_policy") || "new") as LightMeasurementRequest["resume_policy"],
    };
    this.dispatchEvent(new CustomEvent("preflight", { detail: request, bubbles: true, composed: true }));
  }

  private submitGeneric(event: SubmitEvent): void {
    event.preventDefault();
    const definition = this.selectedType ? this.definition(this.selectedType) : undefined;
    if (!definition || !this.capabilities) return;
    const form = new FormData(event.currentTarget as HTMLFormElement);
    const failedDomain = entityDomains(definition, form).find((domain) => this.deviceEntityErrors[domain]);
    if (failedDomain) {
      this.errorMessage = `Could not load ${failedDomain} entities. Retry before starting the measurement.`;
      return;
    }
    const powerEntityId = String(form.get("power_entity_id") ?? "");
    const voltageEntityId = this.matchingVoltageEntityId(powerEntityId) || null;
    const request = buildNonLightRequest(definition, form, this.capabilities, this.powerMeterSpec(powerEntityId, voltageEntityId));
    if (request.measure_type === "charging") {
      const expectedDomain = request.charging_device_type === "lawn_mower_robot" ? "lawn_mower." : "vacuum.";
      if (request.controller.type !== "hass" || !request.controller.entity_id.startsWith(expectedDomain)) {
        this.errorMessage = `Select a ${expectedDomain.slice(0, -1)} entity for the chosen charging device type.`;
        return;
      }
    }
    this.dispatchEvent(new CustomEvent("preflight", { detail: request, bubbles: true, composed: true }));
  }

  private powerMeterSpec(entityId: string, voltageEntityId: string | null = null): PowerMeterSpec {
    if (this.powerMeter === "dummy") return { type: "dummy" };
    if (this.powerMeter === "shelly") return { type: "shelly", device_ip: this.shellyIp };
    return { type: "hass", entity_id: entityId, voltage_entity_id: voltageEntityId };
  }
}

customElements.define("measure-setup-view", SetupView);
