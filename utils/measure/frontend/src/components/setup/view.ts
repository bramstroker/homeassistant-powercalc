import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type {
  Capabilities,
  DummyLoadCalibration,
  DummyLoadSpec,
  EntityDescriptor,
  ErrorHelp,
  FormField,
  MeasureDefinition,
  MeasureParameterName,
  MeasureType,
  MeasurementRequest,
  PowerMeterSpec,
} from "../../types";
import { hasVoltageReading, meterFor } from "../../power-meter";
import type { MeterContext } from "../../power-meter";
import {
  buildMeasurementRequest,
  entityDomain,
  entityDomains,
  narrowingField,
  requestFieldValue,
} from "../../measure-definition";
import { emit } from "../../events";
import { formText } from "../../form";
import { sharedStyles } from "../../styles";
import { defaultDummyLoadMode, dummyLoadSpec, dummyLoadStyles, renderDummyLoad } from "./dummy-load-field";
import { entityListStyles } from "./entity-list-field";
import type { Combobox } from "../shared/combobox";
import {
  renderPowerMeterRequired,
  renderPowerMeterSummary,
  renderTypeChip,
  renderTypePicker,
  setupChromeStyles,
} from "./chrome";
import { errorHelpLink } from "../shared/error-help-link";
import type {
  EntitySelectionChange,
  MultiSelectionChange,
  MultipleLightsChange,
  SelectValueChange,
} from "./fields-section";
import type { ParameterChange } from "./tuning-section";
import "./developer-options";
import "./fields-section";

export { recorderExportFilename } from "./fields-section";

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
    measure-setup-fields-section, measure-setup-developer-options { display: contents; }
    form { display: grid; gap: 1rem; }
    .profile-grid { align-items: start; }
    .device-section { display: grid; gap: 1rem; min-width: 0; }
    .light-grid > measure-combobox, .light-grid > .entity-list, .light-grid > .field-block { grid-column: 1 / -1; }
    .checks { display: flex; flex-wrap: wrap; gap: 0.6rem; }
    .check { min-height: 42px; padding: 0 0.75rem; border: 1px solid var(--line); border-radius: 999px; }
    /* A checkbox pill has no caption above it, so pin it to the input line of its row. */
    .profile-grid > .check { align-self: end; }
    details { border-top: 1px solid var(--line); padding-top: 1rem; }
    summary { width: fit-content; color: var(--signal-strong); cursor: pointer; font-weight: 700; }
    details .grid { margin-top: 1rem; }
    .field-with-help { position: relative; min-width: 0; }
    details.context-help { border: 0; padding: 0; }
    .context-help > summary {
      position: absolute; top: 0; right: 0; display: grid; place-items: center;
      width: 24px; height: 24px; padding: 0; list-style: none;
    }
    .context-help > summary::-webkit-details-marker { display: none; }
    .context-help svg { width: 18px; height: 18px; }
    .help-content {
      position: absolute; top: 1.9rem; right: 0; z-index: 25; width: min(28rem, 100%);
      box-sizing: border-box; padding: 0.85rem 1rem; border: 1px solid var(--line); border-radius: 10px;
      background: var(--surface-raised); box-shadow: 0 10px 28px rgb(0 0 0 / 35%);
      color: var(--ink); font-size: 0.82rem; line-height: 1.5;
    }
    .help-content p { margin: 0; }
    .help-content p + p { margin-top: 0.65rem; }
    .developer-content { display: grid; gap: 0.75rem; margin-top: 0.75rem; }
    .developer-content .notice { margin: 0; }
    .test-mode-status { margin: 0; color: var(--signal-strong); font-size: 0.82rem; }
    .advanced-heading { grid-column: 1 / -1; margin: 0.25rem 0 -0.25rem; color: var(--signal-strong); font-size: 0.76rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; }
    .context p { margin-bottom: 0; }

    .dummy-load { display: grid; gap: 0.9rem; }
    .dummy-load-toggle { width: fit-content; }
    /* A checkbox that reveals or hides a block of the form, rather than submitting a value. */
    .toggle-pill { width: fit-content; }
    .dummy-controller { display: grid; gap: 0.4rem; }
    .dummy-controller p { margin: 0; }
    .multiple-lights { padding-right: 2rem; }
    .multiple-lights .toggle-pill { min-height: 28px; padding: 0; border: 0; border-radius: 0; }
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

  protected async getUpdateComplete(): Promise<boolean> {
    const complete = await super.getUpdateComplete();
    const sections = this.shadowRoot?.querySelectorAll<LitElement>(
      "measure-setup-fields-section, measure-setup-developer-options",
    ) ?? [];
    await Promise.all(Array.from(sections, (section) => section.updateComplete));
    return complete;
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
        ? html`<div class="setup-summary">
            ${renderTypeChip(this.selectedType, this.definition(this.selectedType), this.changeType)}
            ${renderPowerMeterSummary({
              meter: this.meter,
              measureDevice: this.defaultMeasureDevice,
              context: this.meterContext(),
              onOpenSettings: this.openSettings,
            })}
          </div>`
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
    const activeLightCheck = type === "light" && !this.dummyController && !this.dummyLoadEnabled;
    return html`
      <form @submit=${this.submitMeasurement}>
        <measure-setup-fields-section
          .capabilities=${this.capabilities}
          .definition=${definition}
          .definitions=${this.definitions}
          .request=${run}
          .lights=${this.lights}
          .deviceEntities=${this.deviceEntities}
          .deviceEntityErrors=${this.deviceEntityErrors}
          .selectedEntities=${this.selectedEntities}
          .selectValues=${this.selectValues}
          .multiSelection=${this.multiSelection}
          .parameterValues=${this.parameterValues}
          .dummyController=${this.dummyController}
          .multipleLights=${this.multipleLights}
          .derivedCountOverride=${this.derivedCountOverride}
          @entity-selection-change=${this.entitySelectionChanged}
          @select-value-change=${this.selectValueChanged}
          @multi-selection-change=${this.multiSelectionChanged}
          @multiple-lights-change=${this.multipleLightsChanged}
          @derived-count-change=${this.derivedCountChanged}
          @parameter-change=${this.parameterChanged}
        ></measure-setup-fields-section>

        ${this.renderDummyLoadSection(run?.dummy_load)}
        <measure-setup-developer-options
          .developerMode=${this.capabilities.developer_mode ?? false}
          .fastTestMode=${this.capabilities.fast_test_mode ?? false}
          .hasController=${definition.fields.some((field) => field.role === "controller")}
          .dummyController=${this.dummyController}
          @dummy-controller-change=${this.dummyControllerChanged}
        ></measure-setup-developer-options>

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

  private parameterChanged(event: CustomEvent<ParameterChange>): void {
    this.parameterValues = { ...this.parameterValues, [event.detail.name]: event.detail.value };
  }

  private dummyControllerChanged(event: CustomEvent<boolean>): void {
    this.dummyController = event.detail;
  }

  private multipleLightsChanged(event: CustomEvent<MultipleLightsChange>): void {
    this.multipleLights = event.detail.checked;
    if (this.multipleLights) return;
    // Back to one light: keep the first pick so the single selector stays populated, and let the count be derived again.
    this.selectEntities(event.detail.fieldName, this.currentRows(event.detail.fieldName).filter(Boolean).slice(0, 1));
    this.derivedCountOverride = undefined;
  }

  private entitySelectionChanged(event: CustomEvent<EntitySelectionChange>): void {
    this.selectEntities(event.detail.name, event.detail.rows);
  }

  private selectValueChanged(event: CustomEvent<SelectValueChange>): void {
    this.selectValues = { ...this.selectValues, [event.detail.name]: event.detail.value };
  }

  private multiSelectionChanged(event: CustomEvent<MultiSelectionChange>): void {
    this.multiSelection = { ...this.multiSelection, [event.detail.name]: event.detail.values };
  }

  private derivedCountChanged(event: CustomEvent<string>): void {
    this.derivedCountOverride = event.detail;
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

  private definition(type: MeasureType): MeasureDefinition | undefined {
    return this.definitions.find((item) => item.measure_type === type);
  }

  /** Only shared device metadata is safe to use as profile defaults for a multi-device run. */
  private profileDefaults(): { model_id: string; product_name: string; session_name: string } {
    const empty = { model_id: "", product_name: "", session_name: "" };
    if (this.dummyController) return empty;
    const controller = this.selectedType
      ? this.definition(this.selectedType)?.fields.find((field) => field.role === "controller")
      : undefined;
    if (!controller) return empty;
    const entities = [...this.lights, ...Object.values(this.deviceEntities).flat()];
    const ids = this.selectedEntityIds(controller, this.initialRequest);
    const selected = ids.map((id) => entities.find((entity) => entity.entity_id === id));
    const shared = (field: "model_id" | "product_name") => {
      const values = new Set(selected.map((entity) => entity?.[field]));
      return values.size === 1 ? [...values][0] ?? "" : "";
    };
    const modelId = shared("model_id");
    return {
      // An HA model ID can contain characters not allowed in an export path.
      // Leave those for Prepare, which also resolves the original ID from HA.
      model_id: modelId.length <= 120 && /^[A-Za-z0-9][A-Za-z0-9 ._()+-]*$/.test(modelId) ? modelId : "",
      product_name: shared("product_name"),
      session_name: selected.map((entity, index) => entity?.name || ids[index]).join(", ").slice(0, 200),
    };
  }

  private submitMeasurement(event: SubmitEvent): void {
    event.preventDefault();
    const definition = this.selectedType ? this.definition(this.selectedType) : undefined;
    if (!definition || !this.capabilities) return;
    const formElement = event.currentTarget as HTMLFormElement;
    const form = new FormData(formElement);
    this.syncMultiselectValues(formElement, form);
    const failedDomain = this.failedEntityDomain(definition, form);
    if (failedDomain) {
      this.errorMessage = `Could not load ${failedDomain} entities. Retry before starting the measurement.`;
      return;
    }
    // A checkbox group submits nothing at all when it is empty, so require it here.
    const empty = this.missingRequiredMultiselect(definition, form);
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
    const defaults = this.profileDefaults();
    const previous = this.previousRequest(definition, request);
    request.model_id = previous?.model_id || defaults.model_id;
    request.product_name = previous?.product_name || defaults.product_name;
    request.session_name ||= previous?.session_name || defaults.session_name || definition.label;
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

  private failedEntityDomain(definition: MeasureDefinition, form: FormData): string | undefined {
    if (this.dummyController) return undefined;
    return entityDomains(definition, form).find((domain) => this.deviceEntityErrors[domain]);
  }

  private missingRequiredMultiselect(definition: MeasureDefinition, form: FormData): FormField | undefined {
    return definition.fields.find(
      (field) => field.control === "multi_select" && field.required && form.getAll(field.name).length === 0,
    );
  }

  private previousRequest(definition: MeasureDefinition, request: MeasurementRequest): MeasurementRequest | undefined {
    if (this.initialRequest?.measure_type !== definition.measure_type) return undefined;
    if (JSON.stringify(this.initialRequest.controller) !== JSON.stringify(request.controller)) return undefined;
    return this.initialRequest;
  }

  /** Read multiselects explicitly for environments without form-associated custom elements. */
  private syncMultiselectValues(formElement: HTMLFormElement, form: FormData): void {
    for (const picker of formElement.querySelectorAll<Combobox>("measure-combobox[multiple]")) {
      form.delete(picker.name);
      if (picker.disabled || !Array.isArray(picker.value)) continue;
      for (const value of picker.value) form.append(picker.name, value);
    }
  }

  private meterContext(): MeterContext {
    return { powers: this.powers, voltages: this.voltages };
  }


}
