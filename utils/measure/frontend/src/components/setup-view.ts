import { LitElement, css, html, nothing } from "lit";
import type {
  AppSettings,
  Capabilities,
  DummyLoadCalibration,
  DummyLoadSpec,
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
  CONTROLLER_ENTITY_FIELDS,
  deviceFields,
  entityDomain,
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
    dummyLoadCalibration: { attribute: false },
    initialType: { attribute: false },
    defaultPowerEntityId: { type: String },
    defaultMeasureDevice: { type: String },
    powerMeter: { type: String },
    shellyIp: { type: String },
    powerMeterConfigured: { type: Boolean },
    busy: { type: Boolean },
    errorMessage: { type: String },
    selectedType: { state: true },
    selectedLightId: { state: true },
    selectedDeviceEntityId: { state: true },
    selectedChargingType: { state: true },
    dummyLoadEnabled: { state: true },
    dummyLoadMode: { state: true },
    dummyController: { state: true },
  };

  capabilities?: Capabilities;
  definitions: MeasureDefinition[] = [];
  lights: EntityDescriptor[] = [];
  powers: EntityDescriptor[] = [];
  voltages: EntityDescriptor[] = [];
  deviceEntities: Record<string, EntityDescriptor[]> = {};
  deviceEntityErrors: Record<string, string> = {};
  initialRequest?: MeasurementRequest;
  dummyLoadCalibration: DummyLoadCalibration | null = null;
  initialType?: MeasureType;
  defaultPowerEntityId = "";
  defaultMeasureDevice = "";
  powerMeter: AppSettings["power_meter"] = "hass";
  shellyIp = "";
  powerMeterConfigured = true;
  busy = false;
  errorMessage = "";
  selectedType?: MeasureType;
  selectedLightId = "";
  selectedDeviceEntityId = "";
  selectedChargingType = "";
  dummyLoadEnabled = false;
  dummyLoadMode: DummyLoadSpec["mode"] = "calibrate";
  dummyController = false;

  static readonly styles = [sharedStyles, css`
    :host { display: block; min-width: 0; max-width: 100%; }
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
    fieldset { min-width: 0; border: 0; padding: 0; margin: 0; }
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

    .power-meter-required { display: grid; justify-items: start; gap: 0.65rem; margin-top: 1.25rem; padding: 1.1rem; border: 1px solid var(--signal); border-radius: 12px; background: color-mix(in srgb, var(--signal) 8%, var(--field)); }
    .power-meter-required h3, .power-meter-required p { margin: 0; }
    .power-meter-summary { display: flex; align-items: center; gap: 0.8rem; min-width: 0; padding: 0.8rem 0.9rem; border: 1px solid var(--line); border-radius: 10px; background: var(--field); }
    .power-meter-icon { display: grid; place-items: center; flex: 0 0 auto; width: 34px; height: 34px; border-radius: 50%; background: color-mix(in srgb, var(--signal) 14%, transparent); color: var(--signal-strong); font-size: 1.05rem; }
    .power-meter-details { display: grid; gap: 0.12rem; flex: 1; min-width: 0; }
    .power-meter-details strong { overflow-wrap: anywhere; color: var(--ink); font-size: 0.84rem; }
    .power-meter-details span { overflow-wrap: anywhere; color: var(--muted); font-size: 0.78rem; line-height: 1.35; }
    .power-meter-summary button { flex: 0 0 auto; min-height: 38px; padding: 0.4rem 0.9rem; }
    .dummy-load { display: grid; gap: 0.9rem; }
    .dummy-load-toggle { width: fit-content; }
    .dummy-controller { display: grid; gap: 0.4rem; }
    .dummy-controller-toggle { width: fit-content; }
    .dummy-controller p { margin: 0; }
    .dummy-load-options { display: grid; gap: 0.8rem; padding: 0.9rem; border: 1px solid var(--line); border-radius: 10px; background: var(--field); }
    .dummy-load-options p { margin: 0; }
    .calibration-card { display: grid; gap: 0.2rem; }
    .calibration-card strong { color: var(--ink); }
    .calibration-meta { color: var(--muted); font-size: 0.78rem; }
    .choice-list { display: grid; gap: 0.5rem; }
    .choice { display: flex; grid-template-columns: none; align-items: flex-start; gap: 0.55rem; color: var(--ink); }
    .choice input { width: auto; min-height: auto; margin-top: 0.2rem; accent-color: var(--signal); }

    @media (max-width: 640px) {
      .grid { grid-template-columns: 1fr; }
      .context { display: block; }
      .type-grid { grid-template-columns: 1fr; }
      .type-chip { flex-wrap: wrap; }
      .type-chip .chip-body { min-width: calc(100% - 50px); }
      .type-chip button { width: 100%; }
      .power-meter-summary { display: grid; grid-template-columns: 34px minmax(0, 1fr); align-items: start; }
      .power-meter-details { min-width: 0; }
      .power-meter-summary button { grid-column: 1 / -1; width: 100%; }
    }
  `];

  willUpdate(changed: Map<string, unknown>): void {
    // Restore the previously chosen type when returning from the review step.
    if (changed.has("initialType") && this.initialType && this.selectedType === undefined) {
      this.selectedType = this.initialType;
    }
    if (changed.has("initialRequest")) {
      this.dummyLoadEnabled = Boolean(this.initialRequest?.dummy_load);
      this.dummyLoadMode = this.initialRequest?.dummy_load?.mode ?? (this.dummyLoadCalibration ? "reuse" : "calibrate");
      this.dummyController = Boolean(
        this.initialRequest && "controller" in this.initialRequest && this.initialRequest.controller.type === "dummy",
      );
    } else if (changed.has("dummyLoadCalibration") && !this.dummyLoadEnabled) {
      this.dummyLoadMode = this.dummyLoadCalibration ? "reuse" : "calibrate";
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
        ${this.capabilities?.fast_test_mode
          ? html`<p class="notice" role="status"><strong>Fast test mode is enabled.</strong> Dummy light, fan, and charging runs use minimal waits and measurement points. Their output is for app testing only.</p>`
          : nothing}
        ${this.powerMeterConfigured ? this.renderSetupContent() : this.renderPowerMeterRequired()}
      </section>
    `;
  }

  private renderSetupContent() {
    return html`
      ${this.selectedType ? this.renderChip(this.selectedType) : this.renderPicker()}
      ${this.selectedType === LIGHT_TYPE ? this.renderLightForm() : nothing}
      ${this.selectedType && this.selectedType !== LIGHT_TYPE ? this.renderGenericForm(this.selectedType) : nothing}
    `;
  }

  private renderPowerMeterRequired() {
    return html`
      <div class="power-meter-required">
        <h3>Set up your power meter</h3>
        <p class="muted">Choose the power source used for every measurement before creating a profile.</p>
        <button class="primary" type="button" @click=${this.openSettings}>Set up power meter</button>
      </div>
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
          <legend>Measurement device</legend>
          ${this.renderPowerMeterSummary()}
          ${this.renderDummyLoadSection(request?.dummy_load)}
        </fieldset>

        <fieldset class="section">
          <legend>Light profile</legend>
          ${this.renderDummyControllerToggle()}
          <div class="grid profile-grid">
            ${this.dummyController
              ? nothing
              : this.entitySelect("light_entity_id", "Light", this.lights, request?.controller.type === "hass" ? request.controller.entity_id : "", true)}
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
              ${this.numberField("sleep_time", "Settle time (seconds)", request?.parameters.sleep_time ?? defaults.sleep_time, 0, 120, { step: "0.1", hint: "Wait after changing the light before reading power." })}
              ${this.numberField("sample_count", "Samples per point", request?.parameters.sample_count ?? defaults.sample_count, 1, 100, { hint: "More samples reduce noise but increase measurement time.", onInput: this.sampleCountChanged })}
              ${this.numberField("sleep_time_sample", "Time between samples (seconds)", request?.parameters.sleep_time_sample ?? defaults.sleep_time_sample, 0, 120, { hint: "Only used when taking more than one sample.", disabled: (request?.parameters.sample_count ?? defaults.sample_count) <= 1 })}
              ${this.numberField("min_brightness", "Minimum brightness", request?.parameters.min_brightness ?? defaults.min_brightness, 1, 255, { hint: "Increase this when the light does not turn on at its lowest level." })}
              ${this.numberField("sleep_initial", "Initial stabilization (seconds)", request?.parameters.sleep_initial ?? defaults.sleep_initial, 0, 3600)}
              ${this.numberField("sleep_standby", "Standby stabilization (seconds)", request?.parameters.sleep_standby ?? defaults.sleep_standby, 0, 3600)}
              <p class="advanced-heading">Profile resolution</p>
              ${this.numberField("bri_bri_steps", "Brightness mode step", request?.parameters.bri_bri_steps ?? defaults.bri_bri_steps, 1, 255, { hint: "Native brightness increment (1–255).", disabled: !selectedModes.includes("brightness") })}
              ${this.numberField("ct_bri_steps", "Color temperature brightness step", request?.parameters.ct_bri_steps ?? defaults.ct_bri_steps, 1, 255, { hint: "Native brightness increment used while measuring color temperature.", disabled: !selectedModes.includes("color_temp") })}
              ${this.numberField("ct_mired_steps", "Color temperature mired step", request?.parameters.ct_mired_steps ?? defaults.ct_mired_steps, 1, 500, { hint: "Native color-temperature increment in mired.", disabled: !selectedModes.includes("color_temp") })}
              ${this.numberField("hs_bri_steps", "HS brightness step", request?.parameters.hs_bri_steps ?? defaults.hs_bri_steps, 1, 255, { hint: "Native brightness increment used for hue and saturation.", disabled: !selectedModes.includes("hs") })}
              ${this.numberField("hs_hue_steps", "HS hue step", request?.parameters.hs_hue_steps ?? defaults.hs_hue_steps, 1, 65535, { hint: "Native Home Assistant hue increment (0–65535).", disabled: !selectedModes.includes("hs") })}
              ${this.numberField("hs_sat_steps", "HS saturation step", request?.parameters.hs_sat_steps ?? defaults.hs_sat_steps, 1, 255, { hint: "Native saturation increment (1–255).", disabled: !selectedModes.includes("hs") })}
              <div class="grid effect-settings" ?hidden=${!selectedModes.includes("effect")}>
                <p class="advanced-heading">Effect mode</p>
                ${this.numberField("effect_bri_steps", "Effect brightness step", request?.parameters.effect_bri_steps ?? defaults.effect_bri_steps, 1, 255, { hint: "Native brightness increment between long-running effect samples.", disabled: !selectedModes.includes("effect") })}
                ${this.numberField("measure_time_effect_min", "Minimum time per effect (seconds)", request?.parameters.measure_time_effect_min ?? defaults.measure_time_effect_min, 1, 3600, { hint: "An effect can stop after this time once its average converges.", disabled: !selectedModes.includes("effect") })}
                ${this.numberField("measure_time_effect", "Maximum time per effect (seconds)", request?.parameters.measure_time_effect ?? defaults.measure_time_effect, 1, 3600, { hint: "Upper time limit for every effect and brightness combination.", disabled: !selectedModes.includes("effect") })}
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
    return html`
      <form @submit=${this.submitGeneric}>
        <fieldset class="section">
          <legend>Measurement device</legend>
          ${this.renderPowerMeterSummary()}
          ${this.renderDummyLoadSection(run?.dummy_load)}
        </fieldset>

        <fieldset class="section">
          <legend>${definition.label}</legend>
          ${definition.fields.some((field) => CONTROLLER_ENTITY_FIELDS.has(field.name)) ? this.renderDummyControllerToggle() : nothing}
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

  private renderPowerMeterSummary() {
    let source = "Synthetic test meter";
    let detail = "No external readings are used.";
    if (this.powerMeter === "shelly") {
      source = "Shelly power meter";
      detail = this.shellyIp;
    } else if (this.powerMeter === "hass") {
      const entity = this.powers.find((candidate) => candidate.entity_id === this.defaultPowerEntityId);
      source = entity ? `${entity.name} · ${entity.entity_id}` : this.defaultPowerEntityId;
      const voltageEntityId = this.relatedVoltageEntityId(this.defaultPowerEntityId);
      const voltage = this.voltages.find((candidate) => candidate.entity_id === voltageEntityId);
      if (voltageEntityId) {
        const voltageName = voltage ? `${voltage.name} · ` : "";
        detail = `Voltage: ${voltageName}${voltageEntityId}`;
      } else {
        detail = "Home Assistant power sensor";
      }
    }
    return html`
      <div class="power-meter-summary">
        <span class="power-meter-icon" aria-hidden="true">⚡</span>
        <span class="power-meter-details">
          <strong>${source}</strong>
          <span>Measurement device: ${this.defaultMeasureDevice}</span>
          <span>${detail}</span>
        </span>
        <button type="button" @click=${this.openSettings}>Change</button>
      </div>
    `;
  }

  private renderDummyControllerToggle() {
    if (!this.capabilities?.developer_mode) return nothing;
    return html`
      <div class="dummy-controller">
        <label class="check dummy-controller-toggle">
          <input
            type="checkbox"
            name="use_dummy_controller"
            .checked=${this.dummyController}
            @change=${this.dummyControllerChanged}
          />
          Use virtual device (developer)
        </label>
        ${this.dummyController
          ? html`<p class="muted">No real device is controlled during this measurement. Use it only to test the app itself.</p>`
          : nothing}
      </div>
    `;
  }

  private renderDummyLoadSection(request?: DummyLoadSpec | null) {
    if (this.powerMeter === "dummy") return nothing;
    const calibration = this.dummyLoadCalibration;
    const description = request?.description ?? calibration?.description ?? "";
    const voltageAvailable = this.powerMeter !== "hass" || Boolean(this.relatedVoltageEntityId(this.defaultPowerEntityId));
    return html`
      <div class="dummy-load">
        <label class="check dummy-load-toggle">
          <input
            type="checkbox"
            name="use_dummy_load"
            .checked=${this.dummyLoadEnabled}
            ?disabled=${!voltageAvailable}
            @change=${this.dummyLoadEnabledChanged}
          />
          Use resistive dummy load
        </label>
        ${!voltageAvailable
          ? html`<p class="muted">Dummy-load correction requires a voltage sensor associated with the selected power sensor.</p>`
          : nothing}
        ${this.dummyLoadEnabled && voltageAvailable ? this.renderDummyLoadOptions(description) : nothing}
      </div>
    `;
  }

  private renderDummyLoadOptions(description: string) {
    const calibration = this.dummyLoadCalibration;
    return html`
      <div class="dummy-load-options">
        ${calibration ? html`
          <div class="calibration-card">
            <strong>${calibration.description}</strong>
            <span class="calibration-meta">${this.formatResistance(calibration.resistance)} Ω · calibrated ${this.formatCalibrationDate(calibration.calibrated_at)}</span>
          </div>
          <div class="choice-list" role="radiogroup" aria-label="Dummy-load calibration">
            <label class="choice">
              <input type="radio" name="dummy_load_mode" value="reuse" .checked=${this.dummyLoadMode === "reuse"} @change=${this.dummyLoadModeChanged} />
              <span><strong>Use saved calibration</strong><br /><small class="field-hint">Confirm that this exact, preheated load is connected when the measurement starts.</small></span>
            </label>
            <label class="choice">
              <input type="radio" name="dummy_load_mode" value="calibrate" .checked=${this.dummyLoadMode === "calibrate"} @change=${this.dummyLoadModeChanged} />
              <span><strong>Recalibrate</strong><br /><small class="field-hint">Measure the load again before starting this measurement.</small></span>
            </label>
          </div>
        ` : html`
          <input type="hidden" name="dummy_load_mode" value="calibrate" />
          <p class="muted">The dummy load will be calibrated inline before the measurement. Allow at least 10 minutes; an unstable load can take longer.</p>
        `}
        ${this.dummyLoadMode === "calibrate" ? this.textField(
          "dummy_load_description",
          "Dummy-load description",
          description,
          "e.g. 60 W incandescent bulb",
          true,
          "Identify the exact resistive load so the calibration can be safely reused later.",
        ) : nothing}
      </div>
    `;
  }

  private renderGenericTuning(type: MeasureType, request?: NonLightMeasurementRequest) {
    if (!this.capabilities) return nothing;
    const defaults = this.capabilities.defaults;
    const supportsPointSamples = type === "charging" || type === "recorder";
    return html`<details>
      <summary>Advanced timing & quality</summary>
      <div class="grid">
        ${this.numberField("sleep_time", "Reading interval (seconds)", request?.parameters.sleep_time ?? defaults.sleep_time, 0, 120, { step: "0.1", hint: "Delay between repeated power readings and retries." })}
        ${supportsPointSamples
          ? this.numberField("sample_count", "Samples per reading", request?.parameters.sample_count ?? defaults.sample_count, 1, 100, { hint: "More samples reduce noise but increase measurement time.", onInput: this.sampleCountChanged })
          : nothing}
        ${supportsPointSamples
          ? this.numberField("sleep_time_sample", "Time between samples (seconds)", request?.parameters.sleep_time_sample ?? defaults.sleep_time_sample, 0, 120, { hint: "Only used when taking more than one sample.", disabled: (request?.parameters.sample_count ?? defaults.sample_count) <= 1 })
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
    options: { step?: string; hint?: string; disabled?: boolean; onInput?: (event: Event) => void } = {},
  ) {
    const { step = "1", hint = "", disabled = false, onInput = null } = options;
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
    const definition = this.definition(this.selectedType);
    if (!definition) return nothing;
    const name = field.name;
    if (this.dummyController && CONTROLLER_ENTITY_FIELDS.has(name)) return nothing;
    const stored = run && requestFieldValue(run, name);
    if (field.control === "boolean") {
      return html`<label class="check"><input type="checkbox" name=${name} .checked=${Boolean(stored ?? field.default)} />${field.label}</label>`;
    }
    if (field.control === "entity") {
      const value = (stored ?? field.default ?? "").toString();
      const chargingOptions = definition.fields.find((candidate) => candidate.name === "charging_device_type")?.options ?? [];
      const selectedType = this.selectedChargingType
        || (run?.measure_type === "charging" ? run.charging_device_type : chargingOptions[0]?.value);
      const domains = name === "charging_entity_id" ? [entityDomain(definition, field, selectedType)].filter((domain): domain is string => Boolean(domain)) : this.fieldDomains(field);
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
    return field.entity_domains ?? [];
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

  private dummyLoadEnabledChanged(event: Event): void {
    this.dummyLoadEnabled = (event.currentTarget as HTMLInputElement).checked;
    if (this.dummyLoadEnabled) this.dummyLoadMode = this.dummyLoadCalibration ? "reuse" : "calibrate";
  }

  private dummyLoadModeChanged(event: Event): void {
    this.dummyLoadMode = (event.currentTarget as HTMLInputElement).value as DummyLoadSpec["mode"];
  }

  private dummyControllerChanged(event: Event): void {
    this.dummyController = (event.currentTarget as HTMLInputElement).checked;
  }

  private availableModes(request?: LightMeasurementRequest): LutMode[] {
    const supported = this.capabilities?.modes ?? [];
    if (this.dummyController) return supported;
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
    this.dummyController = false;
    this.dispatchEvent(new CustomEvent("measure-type-selected", { detail: type, bubbles: true, composed: true }));
  }

  private changeType(): void {
    this.errorMessage = "";
    this.selectedType = undefined;
  }

  private lightChanged(event: Event): void {
    this.selectedLightId = (event.currentTarget as HTMLSelectElement).value;
  }

  private deviceChanged(event: Event): void {
    this.selectedDeviceEntityId = (event.currentTarget as HTMLSelectElement).value;
  }

  private entityChanged(name: string): ((event: Event) => void) | null {
    if (name === "light_entity_id") return this.lightChanged;
    return this.deviceChanged;
  }

  private openSettings(): void {
    this.dispatchEvent(new CustomEvent("open-settings", { bubbles: true, composed: true }));
  }

  private chargingTypeChanged(event: Event): void {
    this.selectedChargingType = (event.currentTarget as HTMLSelectElement).value;
    const definition = this.definition("charging");
    if (definition) this.dispatchEvent(new CustomEvent("entity-domains-requested", { detail: entityDomains(definition), bubbles: true, composed: true }));
  }

  private definition(type: MeasureType): MeasureDefinition | undefined {
    return this.definitions.find((item) => item.measure_type === type);
  }

  private relatedVoltageEntityId(powerEntityId: string): string {
    return this.powers.find((entity) => entity.entity_id === powerEntityId)?.related_voltage_entity_id ?? "";
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
      measure_device: this.defaultMeasureDevice,
      controller: this.dummyController ? { type: "dummy" } : { type: "hass", entity_id: text("light_entity_id") },
      power_meter: this.powerMeterSpec(),
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
        bri_bri_steps: numberOrDefault("bri_bri_steps"),
        ct_bri_steps: numberOrDefault("ct_bri_steps"),
        ct_mired_steps: numberOrDefault("ct_mired_steps"),
        hs_bri_steps: numberOrDefault("hs_bri_steps"),
        hs_hue_steps: numberOrDefault("hs_hue_steps"),
        hs_sat_steps: numberOrDefault("hs_sat_steps"),
        min_brightness: numberOrDefault("min_brightness"),
        sleep_initial: numberOrDefault("sleep_initial"),
        sleep_standby: numberOrDefault("sleep_standby"),
        effect_bri_steps: numberOrDefault("effect_bri_steps"),
        measure_time_effect: numberOrDefault("measure_time_effect"),
        measure_time_effect_min: numberOrDefault("measure_time_effect_min"),
      },
      resume_policy: (text("resume_policy") || "new") as LightMeasurementRequest["resume_policy"],
      dummy_load: this.dummyLoadSpec(data),
    };
    this.dispatchEvent(new CustomEvent("preflight", { detail: request, bubbles: true, composed: true }));
  }

  private submitGeneric(event: SubmitEvent): void {
    event.preventDefault();
    const definition = this.selectedType ? this.definition(this.selectedType) : undefined;
    if (!definition || !this.capabilities) return;
    const form = new FormData(event.currentTarget as HTMLFormElement);
    const failedDomain = this.dummyController
      ? undefined
      : entityDomains(definition, form).find((domain) => this.deviceEntityErrors[domain]);
    if (failedDomain) {
      this.errorMessage = `Could not load ${failedDomain} entities. Retry before starting the measurement.`;
      return;
    }
    const request = buildNonLightRequest(
      definition,
      form,
      this.capabilities,
      this.powerMeterSpec(),
      this.defaultMeasureDevice,
      this.dummyController,
    );
    request.dummy_load = this.dummyLoadSpec(form);
    if (request.measure_type === "charging" && request.controller.type !== "dummy") {
      const chargingField = definition.fields.find((field) => field.name === "charging_entity_id");
      const expectedDomain = chargingField && entityDomain(definition, chargingField, request.charging_device_type);
      if (!expectedDomain || request.controller.type !== "hass" || !request.controller.entity_id.startsWith(`${expectedDomain}.`)) {
        this.errorMessage = `Select a ${expectedDomain ?? "matching"} entity for the chosen charging device type.`;
        return;
      }
    }
    this.dispatchEvent(new CustomEvent("preflight", { detail: request, bubbles: true, composed: true }));
  }

  private powerMeterSpec(): PowerMeterSpec {
    if (this.powerMeter === "dummy") return { type: "dummy" };
    if (this.powerMeter === "shelly") return { type: "shelly", device_ip: this.shellyIp };
    return {
      type: "hass",
      entity_id: this.defaultPowerEntityId,
      voltage_entity_id: this.relatedVoltageEntityId(this.defaultPowerEntityId) || null,
    };
  }

  private dummyLoadSpec(form: FormData): DummyLoadSpec | undefined {
    if (this.powerMeter === "dummy" || !form.has("use_dummy_load")) return undefined;
    const mode = form.get("dummy_load_mode");
    if (mode === "reuse" && this.dummyLoadCalibration) {
      return {
        mode,
        description: this.dummyLoadCalibration.description,
        resistance: this.dummyLoadCalibration.resistance,
      };
    }
    const description = form.get("dummy_load_description");
    return {
      mode: "calibrate",
      description: typeof description === "string" ? description.trim() : "",
    };
  }

  private formatResistance(resistance: number): string {
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(resistance);
  }

  private formatCalibrationDate(value: string): string {
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? value : date.toLocaleDateString();
  }
}

customElements.define("measure-setup-view", SetupView);
