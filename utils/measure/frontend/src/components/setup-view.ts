import { LitElement, css, html, nothing } from "lit";
import type {
  AppSettings,
  Capabilities,
  DummyLoadCalibration,
  DummyLoadSpec,
  EntityDescriptor,
  ErrorHelp,
  FormField,
  FormFieldOption,
  LutMode,
  MeasureDefaults,
  MeasureDefinition,
  MeasureParameter,
  MeasurementParameters,
  MeasureType,
  MeasurementRequest,
  PowerMeterSpec,
} from "../types";
import {
  buildMeasurementRequest,
  deviceFields,
  enabledParameters,
  entityDomain,
  gatedParameters,
  entityDomains,
  fieldOptions,
  narrowingField,
  requestFieldValue,
} from "../measurement-kinds";
import { sharedStyles } from "../styles";
import { errorHelpLink } from "./error-help-link";

function formText(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value.trim() : "";
}

const FULL_PRODUCT_NAME_HINT = "Enter the complete marketed name, including the series and variant shown on the product or packaging.";
const MULTIPLE_LIGHTS_GUIDE_URL = "https://docs.powercalc.nl/contributing/measure/lights/#multiple-identical-lights";

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
    shellyUsername: { type: String },
    kasaIp: { type: String },
    powerMeterConfigured: { type: Boolean },
    busy: { type: Boolean },
    errorMessage: { type: String },
    errorHelp: { attribute: false },
    selectedType: { state: true },
    selectedEntities: { state: true },
    selectValues: { state: true },
    multiSelection: { state: true },
    parameterValues: { state: true },
    dummyLoadEnabled: { state: true },
    dummyLoadMode: { state: true },
    dummyController: { state: true },
    multipleLights: { state: true },
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
  shellyUsername = "admin";
  kasaIp = "";
  powerMeterConfigured = true;
  busy = false;
  errorMessage = "";
  errorHelp?: ErrorHelp;
  selectedType?: MeasureType;
  /** Entities picked per field. A single-entity field simply holds a one-entry list. */
  selectedEntities: Record<string, string[]> = {};
  selectValues: Record<string, string> = {};
  multiSelection: Record<string, string[]> = {};
  parameterValues: Record<string, string> = {};
  dummyLoadEnabled = false;
  dummyLoadMode: DummyLoadSpec["mode"] = "calibrate";
  dummyController = false;
  multipleLights = false;
  /** Deliberately not reactive: it exists so a typed count survives re-renders instead of being recomputed. */
  private derivedCountOverride?: string;

  static readonly styles = [sharedStyles, css`
    :host { display: block; min-width: 0; max-width: 100%; }
    form { display: grid; gap: 1rem; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
    .profile-grid { align-items: start; }
    .profile-fields { grid-column: 1 / -1; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; gap: 1rem; }
    label, fieldset { display: grid; gap: 0.4rem; }
    label > span, legend, .field-label { color: var(--muted); font-size: 0.82rem; font-weight: 650; }
    .field-hint { color: var(--muted); font-size: 0.74rem; line-height: 1.4; }
    input, select {
      width: 100%; min-height: 44px; border: 1px solid var(--line); border-radius: 9px;
      padding: 0.65rem 0.75rem; background: var(--field); color: var(--ink);
    }
    fieldset { min-width: 0; border: 0; padding: 0; margin: 0; }
    fieldset.section { border: 1px solid var(--line); border-radius: 12px; padding: 1rem 1.1rem 1.2rem; margin: 0; display: grid; gap: 1rem; }
    fieldset.section > legend { padding: 0 0.4rem; color: var(--signal-strong); font-size: 0.85rem; font-weight: 700; }
    .checks { display: flex; flex-wrap: wrap; gap: 0.6rem; }
    .entity-list { display: grid; gap: 0.4rem; }
    .entity-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.5rem; align-items: center; }
    .entity-row button, .add-entity { min-height: 40px; }
    .remove-entity { display: grid; place-items: center; width: 44px; padding: 0; }
    .remove-entity svg { width: 20px; height: 20px; }
    .check { display: flex; grid-template-columns: none; align-items: center; gap: 0.5rem; min-height: 42px; padding: 0 0.75rem; border: 1px solid var(--line); border-radius: 999px; color: var(--ink); }
    .check input { min-height: auto; width: auto; accent-color: var(--signal); }
    /* A checkbox pill has no caption above it, so pin it to the input line of its row. */
    .profile-grid > .check { align-self: end; }
    details { border-top: 1px solid var(--line); padding-top: 1rem; }
    summary { width: fit-content; color: var(--signal-strong); cursor: pointer; font-weight: 700; }
    details .grid { margin-top: 1rem; }
    .advanced-heading { grid-column: 1 / -1; margin: 0.25rem 0 -0.25rem; color: var(--signal-strong); font-size: 0.76rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; }
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
    /* A checkbox that reveals or hides a block of the form, rather than submitting a value. */
    .toggle-pill { width: fit-content; }
    .dummy-controller { display: grid; gap: 0.4rem; }
    .dummy-controller p { margin: 0; }
    .multiple-lights { display: grid; justify-items: start; gap: 0.4rem; }
    .multiple-lights p { margin: 0; }
    .help-link { display: inline-flex; align-items: center; margin-left: 0.25rem; color: var(--signal-strong); vertical-align: 0.15em; }
    .help-link svg { width: 16px; height: 16px; }
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
      this.multipleLights = Boolean(
        this.initialRequest?.measure_type === "light"
        && (this.initialRequest.controller.type === "hass_multi" || this.initialRequest.multiple_light_count > 1),
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
          ? html`<p class="notice" role="status"><strong>Fast test mode is enabled.</strong> Dummy light, fan, speaker and charging runs use minimal waits and measurement points. Their output is for app testing only.</p>`
          : nothing}
        ${this.powerMeterConfigured ? this.renderSetupContent() : this.renderPowerMeterRequired()}
      </section>
    `;
  }

  private renderSetupContent() {
    return html`
      ${this.selectedType ? this.renderChip(this.selectedType) : this.renderPicker()}
      ${this.selectedType ? this.renderMeasurementForm(this.selectedType) : nothing}
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
            <span class="type-icon" aria-hidden="true">${definition.icon}</span>
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
        <span class="type-icon" aria-hidden="true">${definition?.icon ?? ""}</span>
        <span class="chip-body">
          <strong>${definition?.label ?? type}</strong>
          ${definition ? html`<span class="type-desc">${definition.description}</span>` : nothing}
        </span>
        <button type="button" @click=${this.changeType}>Change</button>
      </div>
    `;
  }

  private renderMeasurementForm(type: MeasureType) {
    const definition = this.definition(type);
    if (!definition || !this.capabilities) return html`<p class="muted">Loading measurement capabilities…</p>`;
    const run = this.initialRequest?.measure_type === type ? this.initialRequest : undefined;
    const fields = deviceFields(definition);
    const multipleController = this.multiControllerField();
    // A multi-select needs the room of its own fieldset; the rest are grid cells.
    const blocks = fields.filter((field) => field.control === "multi_select");
    const activeLightCheck = type === "light" && !this.dummyController && !this.dummyLoadEnabled;
    return html`
      <form @submit=${this.submitMeasurement}>
        <fieldset class="section">
          <legend>Measurement device</legend>
          ${this.renderPowerMeterSummary()}
          ${this.renderDummyLoadSection(run?.dummy_load)}
        </fieldset>

        <fieldset class="section">
          <legend>${definition.label}</legend>
          ${definition.fields.some((field) => field.role === "controller") ? this.renderDummyControllerToggle() : nothing}
          ${multipleController && !this.dummyController ? this.renderMultipleLightsToggle(multipleController) : nothing}
          <div class="grid profile-grid">
            ${fields.filter((field) => field.control !== "multi_select").map((field) => this.genericField(field, run))}
            ${definition.supports_profile ? html`<div class="profile-fields">
              ${this.textField("model_id", "Model ID", this.modelId(run), definition.model_id_example && `e.g. ${definition.model_id_example}`, true)}
              ${this.textField("product_name", "Full product name", run?.product_name ?? "", definition.product_name_example || definition.label, true, FULL_PRODUCT_NAME_HINT)}
            </div>` : nothing}
          </div>
          ${blocks.map((field) => this.multiSelectField(field, run))}
        </fieldset>

        ${this.renderTuning(definition, run)}

        ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}${errorHelpLink(this.errorHelp)}</p>` : nothing}
        ${activeLightCheck ? html`
          <p class="muted">The setup check briefly controls the selected light at low-load settings and leaves it off.</p>
        ` : nothing}
        ${activeLightCheck && this.busy ? html`
          <div class="notice" role="status" aria-live="polite">
            <strong>Checking low-load light settings…</strong>
            <p>Testing representative low-load points for the selected brightness, white-channel, and color modes. Each point uses the configured settle, sample, and retry settings.</p>
            <progress aria-label="Low-load light check in progress"></progress>
          </div>
        ` : nothing}
        <div class="actions"><button class="primary" type="submit" ?disabled=${this.busy}>${this.busy
          ? activeLightCheck ? "Checking light and setup…" : "Checking setup…"
          : activeLightCheck ? "Check light and setup" : "Check setup"}</button></div>
      </form>
    `;
  }

  private renderPowerMeterSummary() {
    let source = "Synthetic test meter";
    let detail = "No external readings are used.";
    if (this.powerMeter === "shelly") {
      source = "Shelly power meter";
      detail = this.shellyIp;
    } else if (this.powerMeter === "kasa") {
      source = "Kasa power meter";
      detail = this.kasaIp;
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
        <label class="check toggle-pill">
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

  private renderMultipleLightsToggle(field: FormField) {
    return html`
      <div class="multiple-lights">
        <label class="check toggle-pill">
          <input
            type="checkbox"
            name="measure_multiple_lights"
            .checked=${this.multipleLights}
            data-field=${field.name}
            @change=${this.multipleLightsChanged}
          />
          Measure multiple lights
        </label>
        <p class="muted">
          Measuring multiple identical lights together increases the load, making very low power use easier to measure accurately.
          <a
            class="help-link"
            href=${MULTIPLE_LIGHTS_GUIDE_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Learn more about measuring multiple identical lights"
            title="Learn more"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="9"></circle>
              <path d="M9.75 9a2.4 2.4 0 0 1 4.57 1c0 1.75-2.32 2.1-2.32 3.5M12 17h.01"></path>
            </svg>
          </a>
        </p>
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

  /**
   * Advanced tuning section, built from the parameters the server says this type exposes.
   * A parameter that some option claims is shown only while that option is selected.
   */
  private renderTuning(definition: MeasureDefinition, request?: MeasurementRequest) {
    if (!this.capabilities) return nothing;
    const gated = gatedParameters(definition);
    const active = this.activeParameters(definition, request);
    const shown = definition.parameters.filter((parameter) => !gated.has(parameter.name) || active.has(parameter.name));
    return html`<details>
      <summary>Advanced timing & quality</summary>
      <div class="grid">
        ${definition.supports_resume ? this.resumePolicyField(request) : nothing}
        ${shown.map((parameter, index) => html`
          ${parameter.group && parameter.group !== shown[index - 1]?.group
            ? html`<p class="advanced-heading">${parameter.group}</p>`
            : nothing}
          ${this.parameterField(parameter, request)}
        `)}
      </div>
    </details>`;
  }

  private parameterField(parameter: MeasureParameter, request?: MeasurementRequest) {
    const required = parameter.requires_multiple;
    return this.numberField(parameter.name, parameter.label, this.parameterValue(parameter.name, request), {
      step: parameter.step,
      hint: parameter.hint,
      disabled: required ? Number(this.parameterValue(required, request)) <= 1 : false,
      // Re-render when a parameter that gates another one changes, so the gate keeps up.
      onInput: this.gatesAnother(parameter.name) ? this.parameterChanged : null,
    });
  }

  private resumePolicyField(request?: MeasurementRequest) {
    return html`<label><span>Previous measurement</span><select name="resume_policy">
      <option value="new" ?selected=${(request?.resume_policy ?? "new") === "new"}>Keep it and start a new session</option>
      <option value="overwrite" ?selected=${request?.resume_policy === "overwrite"}>Delete it and start over</option>
    </select></label>`;
  }

  /** What the field should show: what the user typed, else the previous run's, else the default. */
  private parameterValue(name: string, request?: MeasurementRequest): string {
    const stored = request?.parameters[name as keyof MeasurementParameters] ?? this.capabilities?.defaults[name as keyof MeasureDefaults];
    return this.parameterValues[name] ?? String(stored ?? "");
  }

  private gatesAnother(name: string): boolean {
    return this.definitions.some((definition) => definition.parameters.some((parameter) => parameter.requires_multiple === name));
  }

  private parameterChanged(event: Event): void {
    const input = event.currentTarget as HTMLInputElement;
    this.parameterValues = { ...this.parameterValues, [input.name]: input.value };
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
    value: string,
    options: { step?: string; hint?: string; disabled?: boolean; onInput?: ((event: Event) => void) | null } = {},
  ) {
    const { step = "1", hint = "", disabled = false, onInput = null } = options;
    // Bounds come from the capabilities endpoint so the form cannot drift from server-side validation.
    const { min, max } = this.capabilities?.limits?.[name] ?? {};
    return html`<label>
      <span>${label}</span>
      <input type="number" name=${name} .value=${value} min=${min ?? nothing} max=${max ?? nothing} step=${step} required ?disabled=${disabled} @input=${onInput} />
      ${hint ? html`<small class="field-hint">${hint}</small>` : nothing}
    </label>`;
  }

  private entitySelect(name: string, label: string, entities: EntityDescriptor[], selected = "", required = false) {
    return html`
      <label><span>${label}</span><select name=${name} ?required=${required} @change=${this.entityChanged}>
        <option value="">${required ? "Select an entity" : "None"}</option>
        ${entities.map((entity) => html`<option value=${entity.entity_id} ?selected=${entity.entity_id === selected}>${entity.name} · ${entity.entity_id}</option>`)}
      </select></label>
    `;
  }

  private genericField(field: MeasureDefinition["fields"][number], run?: MeasurementRequest) {
    if (!this.selectedType) return nothing;
    const definition = this.definition(this.selectedType);
    if (!definition) return nothing;
    const name = field.name;
    if (this.dummyController && field.role === "controller") return nothing;
    if (field.derived_from) return this.derivedCountField(field, run);
    const stored = run && requestFieldValue(run, field);
    if (field.control === "boolean") {
      return html`<label class="check"><input type="checkbox" name=${name} .checked=${Boolean(stored ?? field.default)} />${field.label}</label>`;
    }
    if (field.control === "entity") {
      const value = (stored ?? field.default ?? "").toString();
      const source = narrowingField(definition, field);
      const domains = source
        ? [entityDomain(definition, field, this.selectValue(source, run))].filter((domain): domain is string => Boolean(domain))
        : this.fieldDomains(field);
      const failed = domains.find((domain) => this.deviceEntityErrors[domain]);
      if (failed) {
        return html`<div class="notice error" role="alert">Could not load ${field.label.toLowerCase()} entities: ${this.deviceEntityErrors[failed]}</div>`;
      }
      const entities = this.entitiesIn(domains);
      if (field.multiple && this.multipleLights) return this.multiEntityField(field, entities, run);
      const selected = field.multiple ? this.selectedEntityId(field, run) || value : value;
      return this.entitySelect(name, field.label, entities, selected, field.required);
    }
    if (field.control === "select") {
      const value = (stored ?? field.default ?? "").toString();
      // Re-render when this select narrows another field, so that field's entities follow.
      const narrows = definition.fields.some((candidate) => candidate.narrowed_by === name);
      return html`<label><span>${field.label}</span><select name=${name} ?required=${field.required} @change=${narrows ? this.selectChanged : null}>
        ${field.options.map((option) => html`<option value=${option.value} ?selected=${option.value === value}>${option.label}</option>`)}
      </select></label>`;
    }
    return this.valueField(field, (stored ?? field.default ?? "").toString());
  }

  /** A plain text or number input, rendered from what the field declares about itself. */
  private valueField(field: FormField, value: string, onInput: ((event: Event) => void) | null = null) {
    return html`<label><span>${field.label}</span><input
      type=${field.control === "number" ? "number" : "text"}
      name=${field.name}
      .value=${value}
      min=${field.minimum ?? nothing}
      max=${field.maximum ?? nothing}
      ?required=${field.required}
      autocomplete="off"
      @input=${onInput}
    />${field.hint ? html`<small class="field-hint">${field.hint}</small>` : nothing}</label>`;
  }

  /**
   * A count that follows how many entities its source field selects. It only means anything
   * while several devices are measured together, so until then it submits a fixed 1 out of sight.
   */
  private derivedCountField(field: FormField, run?: MeasurementRequest) {
    if (!this.multipleLights) return html`<input type="hidden" name=${field.name} value="1" />`;
    const source = this.selectedType
      ? this.definition(this.selectedType)?.fields.find((candidate) => candidate.name === field.derived_from)
      : undefined;
    const derived = source ? this.selectedEntityIds(source, run).length : 0;
    const stored = run && requestFieldValue(run, field);
    const value = this.derivedCountOverride
      ?? (derived > 1 ? String(derived) : (stored ?? field.default ?? "").toString());
    return this.valueField(field, value, this.derivedCountChanged);
  }

  private derivedCountChanged(event: Event): void {
    this.derivedCountOverride = (event.currentTarget as HTMLInputElement).value;
  }

  private multiEntityField(field: FormField, entities: EntityDescriptor[], run?: MeasurementRequest) {
    const rows = this.entityRows(field, run);
    const values = rows.length ? rows : [""];
    return html`<div class="entity-list">
      <span class="field-label">${field.plural_label || field.label}</span>
      ${values.map((value, index) => html`<div class="entity-row">
        <select name=${field.name} required data-index=${index} @change=${this.multiEntityChanged}>
          <option value="">Select an entity</option>
          ${entities.map((entity) => html`<option
            value=${entity.entity_id}
            ?selected=${entity.entity_id === value}
            ?disabled=${entity.entity_id !== value && values.includes(entity.entity_id)}
          >${entity.name} · ${entity.entity_id}</option>`)}
        </select>
        ${values.length > 1 ? html`<button
          class="remove-entity danger"
          type="button"
          data-field=${field.name}
          data-index=${index}
          aria-label="Remove ${field.label}"
          title="Remove ${field.label}"
          @click=${this.removeEntity}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 10v6M14 10v6"></path>
          </svg>
        </button>` : nothing}
      </div>`)}
      <button class="add-entity" type="button" data-field=${field.name} @click=${this.addEntity}>Add another ${field.label.toLowerCase()}</button>
      ${field.hint ? html`<small class="field-hint">${field.hint}</small>` : nothing}
    </div>`;
  }

  private fieldDomains(field: MeasureDefinition["fields"][number]): string[] {
    return field.entity_domains ?? [];
  }

  private multiSelectField(field: FormField, request?: MeasurementRequest) {
    const selected = this.selectedOptions(field, request);
    return html`
      <fieldset>
        <legend>${field.label}</legend>
        <div class="checks">
          ${this.availableOptions(field, request).map((option) => html`
            <label class="check">
              <input
                type="checkbox"
                name=${field.name}
                value=${option.value}
                .checked=${selected.includes(option.value)}
                @change=${this.multiSelectChanged(field)}
              />
              ${option.label}
            </label>
          `)}
        </div>
      </fieldset>
    `;
  }

  private multiSelectChanged(field: FormField): () => void {
    return () => {
      const boxes = [...(this.shadowRoot?.querySelectorAll<HTMLInputElement>(`input[name="${field.name}"]`) ?? [])];
      this.multiSelection = { ...this.multiSelection, [field.name]: boxes.filter((box) => box.checked).map((box) => box.value) };
    };
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

  private multipleLightsChanged(event: Event): void {
    const input = event.currentTarget as HTMLInputElement;
    this.multipleLights = input.checked;
    if (this.multipleLights) return;
    // Back to one light: keep the first pick so the single selector stays populated, and let the count be derived again.
    const field = input.dataset.field ?? "";
    this.selectEntities(field, this.currentRows(field).filter(Boolean).slice(0, 1));
    this.derivedCountOverride = undefined;
  }

  /** Options a field offers right now, narrowed by the capabilities of the entities it names. */
  private availableOptions(field: FormField, request?: MeasurementRequest): FormFieldOption[] {
    // A virtual device stands in for any real one, so it supports everything on offer.
    if (this.dummyController) return field.options;
    return fieldOptions(field, this.narrowedModes(field, request));
  }

  /** Currently selected values: what the user picked, else the previous run's, else everything offered. */
  private selectedOptions(field: FormField, request?: MeasurementRequest): string[] {
    const available = this.availableOptions(field, request).map((option) => option.value);
    const stored = request && requestFieldValue(request, field);
    const chosen = this.multiSelection[field.name] ?? (Array.isArray(stored) && stored.length ? stored : available);
    return available.filter((value) => chosen.includes(value));
  }

  /** Parameters the selected options activate; every other parameter stays disabled. */
  private activeParameters(definition: MeasureDefinition, request?: MeasurementRequest): ReadonlySet<string> {
    const active = new Set<string>();
    for (const field of definition.fields.filter((candidate) => candidate.control === "multi_select")) {
      for (const name of enabledParameters(field, this.selectedOptions(field, request))) active.add(name);
    }
    return active;
  }

  /** Modes every entity named by this field's narrowing source supports; undefined when none is selected. */
  private narrowedModes(field: FormField, request?: MeasurementRequest): LutMode[] | undefined {
    const definition = this.selectedType ? this.definition(this.selectedType) : undefined;
    const source = field.narrowed_by ? definition?.fields.find((candidate) => candidate.name === field.narrowed_by) : undefined;
    if (!source) return undefined;
    const choices = this.entityChoices(source);
    const selected = this.selectedEntityIds(source, request)
      .map((entityId) => choices.find((entity) => entity.entity_id === entityId))
      .filter((entity): entity is EntityDescriptor => Boolean(entity));
    const [first, ...rest] = selected;
    if (!first) return undefined;
    return (first.supported_modes ?? []).filter((mode) => rest.every((entity) => entity.supported_modes?.includes(mode)));
  }

  /** Entities offered for a controller field. Lights arrive with the startup catalog, other domains on demand. */
  private entityChoices(field: FormField): EntityDescriptor[] {
    return this.entitiesIn(this.fieldDomains(field));
  }

  private entitiesIn(domains: string[]): EntityDescriptor[] {
    return domains.flatMap((domain) => (domain === "light" ? this.lights : this.deviceEntities[domain] ?? []));
  }

  /**
   * Rows a field currently shows: what the user picked, else what a previous run stored.
   * Empty rows are kept, because an unanswered select is still a row in the form.
   */
  private entityRows(field: FormField, request?: MeasurementRequest): string[] {
    const chosen = this.selectedEntities[field.name];
    if (chosen) return chosen;
    const stored = request && requestFieldValue(request, field);
    if (Array.isArray(stored)) return stored.map(String);
    return typeof stored === "string" && stored ? [stored] : [];
  }

  private selectedEntityId(field: FormField, request?: MeasurementRequest): string {
    return this.entityRows(field, request)[0] ?? "";
  }

  private selectedEntityIds(field: FormField, request?: MeasurementRequest): string[] {
    return this.entityRows(field, request).filter(Boolean);
  }

  private selectType(type: MeasureType): void {
    this.errorMessage = "";
    this.selectedType = type;
    this.dummyController = false;
    this.multipleLights = false;
    this.dispatchEvent(new CustomEvent("measure-type-selected", { detail: type, bubbles: true, composed: true }));
  }

  private changeType(): void {
    this.errorMessage = "";
    this.selectedType = undefined;
  }



  private entityChanged(event: Event): void {
    const select = event.currentTarget as HTMLSelectElement;
    this.selectEntities(select.name, [select.value]);
  }

  private multiEntityChanged(event: Event): void {
    const select = event.currentTarget as HTMLSelectElement;
    const rows = [...this.currentRows(select.name)];
    rows[Number(select.dataset.index)] = select.value;
    this.selectEntities(select.name, rows);
  }

  private addEntity(event: Event): void {
    const field = (event.currentTarget as HTMLElement).dataset.field ?? "";
    this.selectEntities(field, [...this.currentRows(field), ""]);
  }

  private removeEntity(event: Event): void {
    const button = event.currentTarget as HTMLElement;
    const field = button.dataset.field ?? "";
    const rows = [...this.currentRows(field)];
    rows.splice(Number(button.dataset.index), 1);
    this.selectEntities(field, rows);
  }

  /** Rows as the form currently shows them, so an edit starts from what the user can see. */
  private currentRows(name: string): string[] {
    const field = this.selectedType
      ? this.definition(this.selectedType)?.fields.find((candidate) => candidate.name === name)
      : undefined;
    return field ? this.entityRows(field, this.currentRun) : [];
  }

  /** The previous run, when it belongs to the type now being configured. */
  private get currentRun(): MeasurementRequest | undefined {
    return this.initialRequest?.measure_type === this.selectedType ? this.initialRequest : undefined;
  }

  /** The controller field that accepts several entities at once, when this type has one. */
  private multiControllerField(): FormField | undefined {
    const definition = this.selectedType ? this.definition(this.selectedType) : undefined;
    return definition?.fields.find((field) => field.role === "controller" && field.multiple);
  }

  private selectEntities(name: string, rows: string[]): void {
    this.selectedEntities = { ...this.selectedEntities, [name]: rows };
  }

  private openSettings(): void {
    this.dispatchEvent(new CustomEvent("open-settings", { bubbles: true, composed: true }));
  }

  /**
   * Catch an entity that does not match the domain its narrowing field currently calls for —
   * stale options can survive a change of that field until the entity list reloads.
   */
  private narrowedEntityMismatch(definition: MeasureDefinition, form: FormData): string | undefined {
    for (const field of definition.fields) {
      const source = narrowingField(definition, field);
      if (!source || field.role !== "controller") continue;
      const expected = entityDomain(definition, field, formText(form, source.name));
      const chosen = formText(form, field.name);
      if (!expected || !chosen.startsWith(`${expected}.`)) {
        return `Select a ${expected ?? "matching"} entity for the chosen ${source.label.toLowerCase()}.`;
      }
    }
    return undefined;
  }

  private selectChanged(event: Event): void {
    const select = event.currentTarget as HTMLSelectElement;
    this.selectValues = { ...this.selectValues, [select.name]: select.value };
    const definition = this.selectedType ? this.definition(this.selectedType) : undefined;
    if (definition) this.dispatchEvent(new CustomEvent("entity-domains-requested", { detail: entityDomains(definition), bubbles: true, composed: true }));
  }

  /** Value a narrowing select currently holds: the user's choice, else the previous run's, else its first option. */
  private selectValue(field: FormField, request?: MeasurementRequest): string | undefined {
    const stored = request && requestFieldValue(request, field);
    return this.selectValues[field.name]
      ?? (typeof stored === "string" ? stored : undefined)
      ?? field.options[0]?.value;
  }

  private definition(type: MeasureType): MeasureDefinition | undefined {
    return this.definitions.find((item) => item.measure_type === type);
  }

  private relatedVoltageEntityId(powerEntityId: string): string {
    return this.powers.find((entity) => entity.entity_id === powerEntityId)?.related_voltage_entity_id ?? "";
  }

  /** Model to prefill: the one every selected device reports, or blank when they differ or any is unknown. */
  private modelId(request?: MeasurementRequest): string {
    if (request?.model_id) return request.model_id;
    const controller = this.selectedType
      ? this.definition(this.selectedType)?.fields.find((field) => field.role === "controller")
      : undefined;
    if (!controller) return "";
    const entities = [...this.lights, ...Object.values(this.deviceEntities).flat()];
    const models = new Set(
      this.selectedEntityIds(controller, request)
        .map((entityId) => entities.find((entity) => entity.entity_id === entityId)?.model_id),
    );
    if (models.size !== 1) return "";
    return [...models][0] ?? "";
  }

  private submitMeasurement(event: SubmitEvent): void {
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
    // A checkbox group submits nothing at all when it is empty, so require it here.
    const empty = definition.fields.find(
      (field) => field.control === "multi_select" && field.required && form.getAll(field.name).length === 0,
    );
    if (empty) {
      this.errorMessage = `Select at least one ${empty.label.toLowerCase().replace(/s$/, "")}.`;
      return;
    }
    const request = buildMeasurementRequest(
      definition,
      form,
      this.capabilities,
      this.powerMeterSpec(),
      this.defaultMeasureDevice,
      this.dummyController,
    );
    request.dummy_load = this.dummyLoadSpec(form);
    const mismatch = this.dummyController ? undefined : this.narrowedEntityMismatch(definition, form);
    if (mismatch) {
      this.errorMessage = mismatch;
      return;
    }
    this.dispatchEvent(new CustomEvent("preflight", { detail: request, bubbles: true, composed: true }));
  }

  private powerMeterSpec(): PowerMeterSpec {
    if (this.powerMeter === "dummy") return { type: "dummy" };
    if (this.powerMeter === "shelly") return { type: "shelly", device_ip: this.shellyIp, username: this.shellyUsername };
    if (this.powerMeter === "kasa") return { type: "kasa", device_ip: this.kasaIp };
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
