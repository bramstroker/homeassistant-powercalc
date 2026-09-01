import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type {
  Capabilities,
  DummyLoadCalibration,
  DummyLoadSpec,
  EntityDescriptor,
  ErrorHelp,
  FormField,
  FormFieldOption,
  LutMode,
  MeasureDefinition,
  MeasureParameter,
  MeasureParameterName,
  MeasureType,
  MeasurementRequest,
  PowerMeterSpec,
} from "../types";
import { hasVoltageReading, meterFor } from "../power-meter";
import type { MeterContext } from "../power-meter";
import {
  buildMeasurementRequest,
  deviceFields,
  enabledParameters,
  entityDomain,
  gatedParameters,
  entityDomains,
  fieldVisible,
  fieldOptions,
  narrowingField,
  requestFieldValue,
} from "../measure-definition";
import { emit } from "../events";
import { formText } from "../form";
import { sharedStyles } from "../styles";
import { entitySelect, fieldHint, numberField, textField } from "./fields";
import { defaultDummyLoadMode, dummyLoadSpec, dummyLoadStyles, renderDummyLoad } from "./dummy-load-field";
import { entityListStyles, renderEntityList } from "./entity-list-field";
import {
  renderPowerMeterRequired,
  renderPowerMeterSummary,
  renderTypeChip,
  renderTypePicker,
  setupChromeStyles,
} from "./setup-chrome";
import { errorHelpLink } from "./error-help-link";

const FULL_PRODUCT_NAME_HINT = "Enter the complete marketed name, including the series and variant shown on the product or packaging. Do not repeat the manufacturer name.";
const MULTIPLE_LIGHTS_GUIDE_URL = "https://docs.powercalc.nl/contributing/measure/lights/#multiple-identical-lights";

@customElement("measure-setup-view")
export class SetupView extends LitElement {
  @property({ attribute: false })
  capabilities?: Capabilities;

  @property({ attribute: false })
  definitions: MeasureDefinition[] = [];

  @property({ attribute: false })
  lights: EntityDescriptor[] = [];

  @property({ attribute: false })
  powers: EntityDescriptor[] = [];

  @property({ attribute: false })
  voltages: EntityDescriptor[] = [];

  @property({ attribute: false })
  deviceEntities: Record<string, EntityDescriptor[]> = {};

  @property({ attribute: false })
  deviceEntityErrors: Record<string, string> = {};

  @property({ attribute: false })
  initialRequest?: MeasurementRequest;

  @property({ attribute: false })
  dummyLoadCalibration: DummyLoadCalibration | null = null;

  @property({ attribute: false })
  initialType?: MeasureType;

  /** How the power meter this measurement uses is addressed. */

  @property({ attribute: false })
  meter: PowerMeterSpec = { type: "hass", entity_id: "" };

  @property({ type: String })
  defaultMeasureDevice = "";

  @property({ type: Boolean })
  powerMeterConfigured = true;

  @property({ type: Boolean })
  busy = false;

  @property({ type: String })
  errorMessage = "";

  @property({ attribute: false })
  errorHelp?: ErrorHelp;

  @state()
  selectedType?: MeasureType;

  /** Entities picked per field. A single-entity field simply holds a one-entry list. */

  @state()
  selectedEntities: Record<string, string[]> = {};

  @state()
  selectValues: Record<string, string> = {};

  @state()
  multiSelection: Record<string, string[]> = {};

  @state()
  parameterValues: Partial<Record<MeasureParameterName, string>> = {};

  @state()
  dummyLoadEnabled = false;

  @state()
  dummyLoadMode: DummyLoadSpec["mode"] = "calibrate";

  @state()
  dummyController = false;

  @state()
  multipleLights = false;

  /** Deliberately not reactive: it exists so a typed count survives re-renders instead of being recomputed. */
  private derivedCountOverride?: string;


  static readonly styles = [sharedStyles, dummyLoadStyles, entityListStyles, setupChromeStyles, css`
    :host { display: block; min-width: 0; max-width: 100%; }
    form { display: grid; gap: 1rem; }
    .profile-grid { align-items: start; }
    .profile-fields { grid-column: 1 / -1; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; gap: 1rem; }
    fieldset.section { border: 1px solid var(--line); border-radius: 12px; padding: 1rem 1.1rem 1.2rem; margin: 0; display: grid; gap: 1rem; }
    fieldset.section > legend { padding: 0 0.4rem; color: var(--signal-strong); font-size: 0.85rem; font-weight: 700; }
    .checks { display: flex; flex-wrap: wrap; gap: 0.6rem; }
    .check { min-height: 42px; padding: 0 0.75rem; border: 1px solid var(--line); border-radius: 999px; }
    /* A checkbox pill has no caption above it, so pin it to the input line of its row. */
    .profile-grid > .check { align-self: end; }
    details { border-top: 1px solid var(--line); padding-top: 1rem; }
    summary { width: fit-content; color: var(--signal-strong); cursor: pointer; font-weight: 700; }
    details .grid { margin-top: 1rem; }
    .advanced-heading { grid-column: 1 / -1; margin: 0.25rem 0 -0.25rem; color: var(--signal-strong); font-size: 0.76rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; }
    .context p { margin-bottom: 0; }

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
    .field-block { display: grid; gap: 0.45rem; }
    .field-block .field-hint, .select-guidance p { margin: 0; }
    .select-guidance { display: grid; gap: 0.35rem; }
    .select-guidance ul { margin: 0.1rem 0 0; padding-left: 1.2rem; color: var(--muted); font-size: 0.82rem; }

    @media (max-width: 640px) {
      .context { display: block; }
    }
  `];

  willUpdate(changed: Map<string, unknown>): void {
    // Restore the previously chosen type when returning from the review step.
    if (changed.has("initialType") && this.initialType && this.selectedType === undefined) {
      this.selectedType = this.initialType;
    }
    if (changed.has("initialRequest")) {
      const controller = this.initialRequest && "controller" in this.initialRequest
        ? this.initialRequest.controller
        : undefined;
      this.dummyLoadEnabled = Boolean(this.initialRequest?.dummy_load);
      this.dummyLoadMode = this.initialRequest?.dummy_load?.mode ?? defaultDummyLoadMode(this.dummyLoadCalibration);
      this.dummyController = controller?.type === "dummy";
      this.multipleLights = Boolean(
        this.initialRequest?.measure_type === "light"
        && (this.initialRequest.controller.type === "hass_multi" || this.initialRequest.multiple_light_count > 1),
      );
    } else if (changed.has("dummyLoadCalibration") && !this.dummyLoadEnabled) {
      this.dummyLoadMode = defaultDummyLoadMode(this.dummyLoadCalibration);
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
        ${this.initialRequest ? html`<p class="notice" role="status">
          This draft uses the selected session's measurement device and power-meter configuration.
          <button type="button" @click=${this.useCurrentSettings}>Use current app defaults</button>
        </p>` : nothing}
        ${this.powerMeterConfigured ? this.renderSetupContent() : renderPowerMeterRequired(this.openSettings)}
      </section>
    `;
  }

  private renderSetupContent() {
    return html`
      ${this.selectedType
        ? renderTypeChip(this.selectedType, this.definition(this.selectedType), this.changeType)
        : renderTypePicker(this.definitions, this.selectType)}
      ${this.selectedType ? this.renderMeasurementForm(this.selectedType) : nothing}
    `;
  }

  private useCurrentSettings(): void {
    emit(this, "use-current-settings");
  }

  private renderMeasurementForm(type: MeasureType) {
    const definition = this.definition(type);
    if (!definition || !this.capabilities) return html`<p class="muted">Loading measurement capabilities…</p>`;
    const run = this.initialRequest?.measure_type === type ? this.initialRequest : undefined;
    const fields = deviceFields(definition);
    const multipleController = this.multiControllerField();
    const showProfileFields = definition.supports_profile
      || (type === "recorder" && this.recorderPurpose(run) === "complex_profile");
    // A multi-select needs the room of its own fieldset; the rest are grid cells.
    const blocks = fields.filter((field) => field.control === "multi_select" && this.isFieldVisible(field, run));
    const activeLightCheck = type === "light" && !this.dummyController && !this.dummyLoadEnabled;
    return html`
      <form @submit=${this.submitMeasurement}>
        <fieldset class="section">
          <legend>Measurement device</legend>
          ${renderPowerMeterSummary({
            meter: this.meter,
            measureDevice: this.defaultMeasureDevice,
            context: this.meterContext(),
            onOpenSettings: this.openSettings,
          })}
          ${this.renderDummyLoadSection(run?.dummy_load)}
        </fieldset>

        <fieldset class="section">
          <legend>${definition.label}</legend>
          ${definition.fields.some((field) => field.role === "controller") ? this.renderDummyControllerToggle() : nothing}
          ${multipleController && !this.dummyController ? this.renderMultipleLightsToggle(multipleController) : nothing}
          <div class="grid profile-grid">
            ${fields.filter((field) => field.control !== "multi_select").map((field) => this.genericField(field, run))}
            ${showProfileFields ? html`<div class="profile-fields">
              ${textField("model_id", "Model ID", {
                value: this.modelId(run),
                placeholder: definition.model_id_example && `e.g. ${definition.model_id_example}`,
                required: true,
              })}
              ${textField("product_name", "Full product name", {
                value: run?.product_name ?? "",
                placeholder: definition.product_name_example || definition.label,
                required: true,
                hint: FULL_PRODUCT_NAME_HINT,
              })}
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

  private renderDummyLoadSection(stored?: DummyLoadSpec | null) {
    if (!meterFor(this.meter.type).supportsDummyLoad) return nothing;
    return renderDummyLoad({
      calibration: this.dummyLoadCalibration,
      stored,
      enabled: this.dummyLoadEnabled,
      mode: this.dummyLoadMode,
      voltageAvailable: hasVoltageReading(this.meter),
      onToggle: this.dummyLoadEnabledChanged,
      onModeChange: this.dummyLoadModeChanged,
    });
  }

  private dummyLoadEnabledChanged(event: Event): void {
    this.dummyLoadEnabled = (event.currentTarget as HTMLInputElement).checked;
    if (this.dummyLoadEnabled) this.dummyLoadMode = defaultDummyLoadMode(this.dummyLoadCalibration);
  }

  private dummyLoadModeChanged(event: Event): void {
    this.dummyLoadMode = (event.currentTarget as HTMLInputElement).value as DummyLoadSpec["mode"];
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
    const gate = parameter.requires_multiple;
    // Bounds come from the capabilities endpoint so the form cannot drift from server-side validation.
    const { min, max } = this.capabilities?.limits?.[parameter.name] ?? {};
    return numberField(parameter.name, parameter.label, this.parameterValue(parameter.name, request), {
      min,
      max,
      step: parameter.step,
      hint: parameter.hint,
      disabled: gate ? Number(this.parameterValue(gate, request)) <= 1 : false,
      // Re-render when a parameter that gates another one changes, so the gate keeps up.
      onInput: this.gatesAnother(parameter.name) ? this.parameterChanged : null,
    });
  }

  /** What the field should show: what the user typed, else the previous run's, else the default. */
  private parameterValue(name: MeasureParameterName, request?: MeasurementRequest): string {
    const stored = request?.parameters[name] ?? this.capabilities?.defaults[name];
    return this.parameterValues[name] ?? String(stored ?? "");
  }

  private gatesAnother(name: MeasureParameterName): boolean {
    return this.definitions.some((definition) => definition.parameters.some((parameter) => parameter.requires_multiple === name));
  }

  private parameterChanged(event: Event): void {
    const input = event.currentTarget as HTMLInputElement;
    this.parameterValues = { ...this.parameterValues, [input.name as MeasureParameterName]: input.value };
  }


  private genericField(field: MeasureDefinition["fields"][number], run?: MeasurementRequest) {
    if (!this.selectedType) return nothing;
    const definition = this.definition(this.selectedType);
    if (!definition) return nothing;
    if (!this.isFieldVisible(field, run)) return nothing;
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
      // An all-entities field reads the "*" catalog; its declared domains only filter that
      // catalog client-side, so a stale error from another measure type must not surface here.
      const failed = field.all_entities
        ? (this.deviceEntityErrors["*"] ? "*" : undefined)
        : domains.find((domain) => this.deviceEntityErrors[domain]);
      if (failed) {
        return html`<div class="notice error" role="alert">Could not load ${field.label.toLowerCase()} entities: ${this.deviceEntityErrors[failed]}</div>`;
      }
      const entities = this.entityChoices(field, domains, run);
      if (field.multiple && (field.role !== "controller" || this.multipleLights)) {
        return this.multiEntityField(field, entities, run);
      }
      let selected = field.multiple ? this.selectedEntityId(field, run) || value : value;
      if (!selected && field.same_device_only && entities.length === 1) selected = entities[0]?.entity_id ?? "";
      const relatedMissing = Boolean(field.same_device_only && this.relatedEntity(field, run) && entities.length === 0);
      const selector = entitySelect(name, field.label, entities, { selected, required: field.required, onChange: this.entityChanged });
      if (!field.hint && !relatedMissing) return selector;
      return html`<div class="field-block">
        ${selector}
        ${fieldHint(field.hint ?? "")}
        ${relatedMissing ? html`<p class="notice error" role="alert">No usable battery percentage sensor was found on the same Home Assistant device. PowerCalc vacuum profiles require one; expose or add that sensor before recording.</p>` : nothing}
      </div>`;
    }
    if (field.control === "select") {
      const value = this.selectValue(field, run) ?? (stored ?? field.default ?? "").toString();
      // Re-render when this select narrows another field, so that field's entities follow.
      const affectsAnother = definition.fields.some(
        (candidate) => candidate.narrowed_by === name || Object.hasOwn(candidate.visible_when ?? {}, name),
      );
      const selectedOption = field.options.find((option) => option.value === value);
      return html`<div class="field-block"><label><span>${field.label}</span><select name=${name} ?required=${field.required} @change=${affectsAnother ? this.selectChanged : null}>
        ${field.options.map((option) => html`<option value=${option.value} ?selected=${option.value === value}>${option.label}</option>`)}
      </select></label>${this.optionGuidance(selectedOption)}</div>`;
    }
    if (name === "export_filename" && this.selectedType === "recorder") {
      return this.valueField(field, recorderExportFilename(this.recorderPurpose(run), (stored ?? field.default ?? "").toString()));
    }
    return this.valueField(field, (stored ?? field.default ?? "").toString());
  }

  private recorderPurpose(request?: MeasurementRequest): string | undefined {
    if (this.selectedType !== "recorder") return undefined;
    if (this.selectValues.recorder_purpose) return this.selectValues.recorder_purpose;
    if (request?.measure_type === "recorder") return request.recorder_purpose;
    return this.definition("recorder")?.fields.find((field) => field.name === "recorder_purpose")?.default?.toString();
  }

  private isFieldVisible(field: FormField, request?: MeasurementRequest): boolean {
    const definition = this.selectedType ? this.definition(this.selectedType) : undefined;
    return fieldVisible(field, (name) => {
      const source = definition?.fields.find((candidate) => candidate.name === name);
      if (!source) return "";
      if (source.control === "select") return this.selectValue(source, request) ?? "";
      const stored = request && requestFieldValue(request, source);
      return this.selectedEntityId(source, request) || (typeof stored === "string" ? stored : "");
    });
  }

  private optionGuidance(option?: FormFieldOption) {
    if (!option?.description && !option?.guidance?.length) return nothing;
    const guidanceItems = option.guidance?.map((item) => html`<li>${item}</li>`);
    return html`<div class="select-guidance">
      ${option.description ? html`<p class="muted">${option.description}</p>` : nothing}
      ${guidanceItems?.length ? html`<ul>${guidanceItems}</ul>` : nothing}
    </div>`;
  }

  /** A plain text or number input, rendered from what the field declares about itself. */
  private valueField(field: FormField, value: string, onInput: ((event: Event) => void) | null = null) {
    return html`<label><span>${field.label}</span><input
      type=${field.control === "number" ? "number" : "text"}
      name=${field.name}
      min=${field.minimum ?? nothing}
      max=${field.maximum ?? nothing}
      .value=${value}
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
    return renderEntityList({
      field,
      entities,
      rows: this.entityRows(field, run),
      onChange: (rows) => this.selectEntities(field.name, rows),
    });
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
  private entityChoices(field: FormField, domains = this.fieldDomains(field), request?: MeasurementRequest): EntityDescriptor[] {
    let entities = field.all_entities ? [...(this.deviceEntities["*"] ?? [])] : this.entitiesIn(domains);
    if (field.all_entities && domains.length) {
      entities = entities.filter((entity) => entity.domain && domains.includes(entity.domain));
    }
    if (field.entity_device_classes?.length) {
      entities = entities.filter((entity) => this.matchesDeviceClass(entity, field.entity_device_classes ?? []));
    }
    const related = this.relatedEntity(field, request);
    if (!related?.device_id) return field.same_device_only ? [] : entities;
    if (field.same_device_only) return entities.filter((entity) => entity.device_id === related.device_id);
    return entities.sort((left, right) => Number(right.device_id === related.device_id) - Number(left.device_id === related.device_id));
  }

  private matchesDeviceClass(entity: EntityDescriptor, deviceClasses: readonly string[]): boolean {
    if (!entity.device_class || !deviceClasses.includes(entity.device_class)) return false;
    if (entity.device_class !== "battery") return true;
    return entity.domain === "sensor"
      && entity.unit === "%"
      && !["unavailable", "unknown", "none"].includes((entity.state ?? "").toLowerCase())
      && Number.isFinite(Number(entity.state));
  }

  private relatedEntity(field: FormField, request?: MeasurementRequest): EntityDescriptor | undefined {
    if (!field.related_to || !this.selectedType) return undefined;
    const source = this.definition(this.selectedType)?.fields.find((candidate) => candidate.name === field.related_to);
    if (!source) return undefined;
    const entityId = this.selectedEntityId(source, request);
    return (this.deviceEntities["*"] ?? []).find((entity) => entity.entity_id === entityId);
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

  private readonly selectType = (type: MeasureType): void => {
    this.errorMessage = "";
    this.selectedType = type;
    this.dummyController = false;
    this.multipleLights = false;
    emit<MeasureType>(this, "measure-type-selected", type);
  };

  private readonly changeType = (): void => {
    this.errorMessage = "";
    this.selectedType = undefined;
  };



  private entityChanged(event: Event): void {
    const select = event.currentTarget as HTMLSelectElement;
    this.selectEntities(select.name, [select.value]);
    const definition = this.selectedType ? this.definition(this.selectedType) : undefined;
    for (const dependent of definition?.fields.filter((field) => field.related_to === select.name) ?? []) {
      this.selectEntities(dependent.name, []);
    }
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

  private readonly openSettings = (): void => {
    emit(this, "open-settings");
  };

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
    const form = select.closest("form");
    if (definition) emit<string[]>(this, "entity-domains-requested", entityDomains(definition, form ? new FormData(form) : undefined));
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
      this.meter,
      this.defaultMeasureDevice,
      this.dummyController,
    );
    request.dummy_load = meterFor(this.meter.type).supportsDummyLoad
      ? dummyLoadSpec(form, this.dummyLoadCalibration)
      : undefined;
    const mismatch = this.dummyController ? undefined : this.narrowedEntityMismatch(definition, form);
    if (mismatch) {
      this.errorMessage = mismatch;
      return;
    }
    emit<MeasurementRequest>(this, "preflight", request);
  }

  private meterContext(): MeterContext {
    return { powers: this.powers, voltages: this.voltages };
  }


}

/**
 * The export filename a recorder purpose implies. Both the server and the result plotter
 * pick the format by extension, so the name follows the purpose rather than whatever a
 * duplicated session left behind. An unrecognised extension is the user's own, and stays.
 */
export function recorderExportFilename(purpose: string | undefined, name: string): string {
  const wanted = purpose === "complex_profile" ? "jsonl" : "csv";
  if (!name) return `record.${wanted}`;
  const dot = name.lastIndexOf(".");
  const current = dot === -1 ? "" : name.slice(dot + 1).toLowerCase();
  if (current !== "csv" && current !== "jsonl") return name;
  return current === wanted ? name : `${name.slice(0, dot)}.${wanted}`;
}
