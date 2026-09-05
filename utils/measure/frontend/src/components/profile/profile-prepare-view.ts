import { LitElement, css, html, nothing } from "lit";
import type { PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { guard } from "lit/directives/guard.js";
import type {
  ContributionAuthState,
  ContributionDraft,
  ContributionDraftFile,
  ContributionFormValues,
  ContributionPreview,
  ContributionPreviewRequest,
  DeviceSpecificationField,
  SessionSnapshot,
} from "../../types";
import { emit } from "../../events";
import { fileSize, words } from "../../format";
import { formText } from "../../form";
import { metadataLabels, validateMetadata } from "../../profile-validation";
import { sharedStyles } from "../../styles";
import "../shared/combobox";

@customElement("measure-profile-prepare-view")
export class ProfilePrepareView extends LitElement {
  @property({ attribute: false }) snapshot!: SessionSnapshot;
  @property({ attribute: false }) contributionAuth?: ContributionAuthState;
  @property({ attribute: false }) contributionDraft?: ContributionPreview;
  @property({ attribute: false }) contributionFormValues: ContributionFormValues = {};
  @property({ attribute: false }) contributionPreview?: ContributionPreview;
  @property({ type: Boolean }) contributionBusy = false;
  @property({ type: String }) contributionError = "";
  @property({ type: String }) contributionErrorField?: string;
  @property({ attribute: false }) manufacturers: string[] = [];
  @property({ attribute: false }) measureDevices: string[] = [];
  @property({ type: Boolean }) measureDevicesLoading = false;
  @property({ type: String }) measureDevicesError = "";
  @property({ attribute: false }) deviceSpecificationFields: Record<string, DeviceSpecificationField[]> = {};

  @state()
  private contributionEdit?: ContributionPreviewRequest;

  @state()
  private fieldErrors: Record<string, string> = {};

  @state()
  previewDirty = false;

  private dismissedServerField?: string;

  protected willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("snapshot") && changed.get("snapshot")?.session_id !== this.snapshot?.session_id) {
      if (this.hasUpdated) this.contributionFormValues = {};
      this.contributionEdit = undefined;
      this.fieldErrors = {};
      this.previewDirty = false;
      this.dismissedServerField = undefined;
    }
    if (changed.has("contributionPreview") && this.contributionPreview) {
      if (this.hasUpdated) this.contributionFormValues = {};
      this.contributionEdit = undefined;
      this.previewDirty = false;
      this.fieldErrors = {};
    }
    this.previewDirty = Object.keys(this.contributionFormValues).length > 0 || this.previewDirty;
    if (changed.has("contributionBusy") && this.contributionBusy) this.dismissedServerField = undefined;
  }

  protected updated(changed: PropertyValues<this>): void {
    if (changed.has("contributionError") && this.contributionError) this.focusValidation();
  }

  static readonly styles = [sharedStyles, css`
    .profile-guidance { max-width: 1000px; line-height: 1.55; }
    .manufacturer-library-link { white-space: nowrap; }
    .contribution { margin-top: 1.5rem; }
    .profile-metadata { padding: 0; border: 0; border-radius: 0; background: transparent; }
    .contribution-auto { padding: clamp(0.85rem, 3vw, 1.2rem); border: 1px solid var(--line); border-radius: 12px; background: color-mix(in srgb, var(--field) 68%, transparent); }
    .contribution-form { display: grid; }
    .validation-footer { display: flex; align-items: center; justify-content: space-between; gap: 1.25rem; margin-top: 1.5rem; padding: 1rem 1.1rem; border: 1px solid var(--line); border-radius: 12px; background: color-mix(in srgb, var(--field) 72%, transparent); }
    .validation-status { margin: 0; color: var(--muted); line-height: 1.45; }
    .validation-status.pending { color: var(--ink); }
    .validation-status.valid { color: var(--good); font-weight: 650; }
    .validation-footer button { flex: 0 0 auto; }
    .validation-summary { margin: 0 0 1rem; }
    .validation-summary ul { display: block; margin: 0.5rem 0 0; padding-left: 1.25rem; }
    .validation-summary li { display: list-item; padding: 0.15rem 0; border: 0; }
    .validation-summary button { min-height: 0; padding: 0; border: 0; background: transparent; color: inherit; text-align: left; text-decoration: underline; font: inherit; }
    .required-guidance { margin: 0 0 1rem; font-size: 0.8rem; }
    .metadata-group { min-inline-size: 0; margin: 0; padding: 0; border: 0; border-top: 1px solid var(--line); }
    .metadata-group legend { padding: 0 0.65rem 0 0; color: var(--ink); font-size: 1rem; font-weight: 700; }
    .metadata-group-body { display: grid; gap: 0.8rem; padding: 0.75rem 0 1.5rem; }
    .metadata-group-description { margin: 0; color: var(--muted); font-size: 0.8rem; }
    .contribution-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.8rem; align-items: start; }
    .contribution-grid.contributor-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .contribution-grid > *, .contribution-grid label, .notes-field { align-self: start; }
    .contribution-grid label, .notes-field { display: grid; gap: 0.4rem; }
    .contribution-grid label > span, .notes-field > span { color: var(--muted); font-size: 0.82rem; font-weight: 650; }
    .field-stack { display: grid; gap: 0.4rem; min-width: 0; }
    textarea { min-height: 84px; resize: vertical; }
    .profile-details { min-width: 0; }
    .profile-details summary { padding: 0.6rem 0; color: var(--muted); cursor: pointer; font-size: 0.82rem; }
    .profile-details summary:hover { color: var(--ink); }
    .profile-details-body { display: grid; gap: 1rem; padding: 0.5rem 0; }
    .prepared-preview { margin-top: 1rem; }
    .preparation-warning { margin: 1rem 0 0; }
    .preview-block { display: grid; gap: 0.45rem; min-width: 0; }
    .preview-block span, .info-list span { color: var(--muted); font-size: 0.76rem; font-weight: 650; }
    .info-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 0.5rem 0.8rem; margin: 0; }
    .info-list div { min-width: 0; }
    .info-list dd { margin: 0.15rem 0 0; overflow-wrap: anywhere; }
    pre { max-height: 240px; overflow: auto; margin: 0; padding: 0.8rem; border: 1px solid var(--line); border-radius: 10px; background: var(--well); color: var(--ink); font-size: 0.75rem; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; }
    a { color: var(--signal-strong); font-weight: 700; }
    @media (max-width: 520px) {
      .contribution-grid, .contribution-grid.contributor-grid { grid-template-columns: 1fr; }
      .validation-footer { align-items: stretch; flex-direction: column; }
      .validation-footer button { width: 100%; }
    }
  `];

  render() {
    const libraryUrl = this.contributionPreview?.manufacturer_library_url ?? this.contributionDraft?.manufacturer_library_url;
    return html`
      <section class="panel" aria-labelledby="profile-title">
        <p class="eyebrow">05 / Prepare</p>
        <h2 id="profile-title">Prepare your Powercalc profile</h2>
        <p class="muted profile-guidance">
          Review and enrich the metadata added to model.json.
          ${libraryUrl
            ? html`Check the <a class="manufacturer-library-link" href=${libraryUrl} target="_blank" rel="noopener noreferrer">existing manufacturer profiles <span aria-hidden="true">↗</span></a> and match the naming and metadata patterns used there.`
            : nothing}
        </p>
        ${this.renderPreparationSection()}
        <div class="actions"><button type="button" @click=${() => emit(this, "back")}>Back to result</button></div>
      </section>`;
  }

  private renderPreparationSection() {
    if (this.snapshot.state !== "completed") return nothing;
    return html`<section class="contribution profile-metadata">${this.renderPreparationPanel()}</section>`;
  }

  private renderPreparationPanel() {
    const draft = this.editableDraft();
    if (!draft?.eligible) {
      return html`<div class="contribution-auto"><p class="muted">${draft?.reason ?? "This measurement cannot be prepared as a profile."}</p></div>`;
    }
    return html`
      <div class="contribution-auto">
        <form class="contribution-form" novalidate @submit=${this.previewContribution}
          @input=${this.metadataChanged} @change=${this.metadataChanged}
          @focusout=${this.validateField}
          @combobox-change=${this.metadataChanged}>
          ${this.renderValidationSummary()}
          <p class="muted required-guidance">Fields marked <span class="required-marker" aria-hidden="true">*</span><span class="sr-only">with an asterisk</span> are required.</p>
          ${this.renderProductMetadata(draft)}
          ${this.renderContributorMetadata(draft)}
          ${this.renderMeasurementMetadata(draft)}
          ${this.renderDeviceSpecifications(draft)}
          ${this.renderContributionNotes(draft)}
          ${this.renderMeasurementContext(draft)}
          ${this.renderValidationFooter()}
        </form>
        ${this.contributionPreview && this.canContinue() ? this.renderPreparedPreview(this.contributionPreview) : nothing}
      </div>`;
  }

  private renderProductMetadata(draft: ContributionDraft) {
    const manufacturer = this.fieldValue("manufacturer_name", draft.manufacturer_name);
    return html`<fieldset class="metadata-group" ?disabled=${this.contributionBusy}>
      <legend>Product</legend>
      <div class="metadata-group-body">
        <p class="metadata-group-description">Identity and manufacturer details used to place and discover this profile.</p>
        <div class="contribution-grid">
          <div class="field-stack">
            <measure-combobox name="manufacturer_name" label="Manufacturer"
              .error=${this.fieldError("manufacturer_name")} ?disabled=${this.contributionBusy}
              .value=${manufacturer}
              .options=${this.manufacturers.map((name) => ({ value: name, label: name }))}
              placeholder="Search or enter a manufacturer" hint="Choose an existing manufacturer or enter a new one."
              required allowCustom>
              <input slot="value" type="hidden" name="manufacturer_name" .value=${manufacturer} />
            </measure-combobox>
          </div>
          ${this.input("model_id", "Model ID", draft.model_id)}
          ${this.input("product_name", "Product name", draft.product_name, {
            hint: "Use the marketed name without repeating the manufacturer, e.g. “Hue White Ambiance GU10”.",
          })}
          ${this.input("product_url", "Manufacturer product URL", draft.product_url ?? "", { required: false, placeholder: "https://…" })}
          ${this.input("aliases", "Model aliases", (draft.aliases ?? []).join(", "), { required: false, placeholder: "Comma separated" })}
          ${this.input("gtins", "GTIN / barcodes", (draft.gtins ?? []).join(", "), { required: false, placeholder: "Comma separated" })}
        </div>
      </div>
    </fieldset>`;
  }

  private renderContributorMetadata(draft: ContributionDraft) {
    return html`<fieldset class="metadata-group" ?disabled=${this.contributionBusy}>
      <legend>Contributor</legend>
      <div class="metadata-group-body">
        <p class="metadata-group-description">These details are prefilled from your profile settings and credited in model.json.</p>
        <div class="contribution-grid contributor-grid">
          ${this.input("contributor", "Name", draft.contributor)}
          ${this.input("contributor_github", "GitHub username", draft.contributor_github ?? this.contributionAuth?.identity?.login ?? "")}
          ${this.input("contributor_email", "Email", draft.contributor_email ?? "", { required: false })}
        </div>
      </div>
    </fieldset>`;
  }

  private renderMeasurementMetadata(draft: ContributionDraft) {
    const measureDevice = this.fieldValue("measure_device", draft.measure_device);
    const hint = this.measureDevicesLoading
      ? "Loading names used by existing Powercalc profiles…"
      : "Choose an existing power meter or enter its manufacturer and model.";
    return html`<fieldset class="metadata-group" ?disabled=${this.contributionBusy}>
      <legend>Measurement</legend>
      <div class="metadata-group-body">
        <p class="metadata-group-description">Document the equipment and method used to create the profile.</p>
        <div class="contribution-grid">
          <div class="field-stack">
            <measure-combobox name="measure_device" label="Measurement device"
              .value=${measureDevice}
              .options=${this.measureDevices.map((device) => ({ value: device, label: device }))}
              .error=${this.fieldError("measure_device")} ?disabled=${this.contributionBusy}
              placeholder="e.g. Shelly Plug S" .hint=${hint} required allowCustom>
              <input slot="value" type="hidden" name="measure_device" .value=${measureDevice} />
            </measure-combobox>
            ${this.measureDevicesError
              ? html`<small class="field-hint error" role="status">Library suggestions are unavailable; manual entry still works.</small>`
              : nothing}
          </div>
          ${this.input("measure_device_firmware", "Device firmware", draft.measure_device_firmware ?? "", { required: false })}
          ${this.renderMainsVoltage(draft)}
        </div>
        ${this.renderTextarea("measure_description", "Measurement description", draft.measure_description)}
      </div>
    </fieldset>`;
  }

  private renderContributionNotes(draft: ContributionDraft) {
    return html`<fieldset class="metadata-group" ?disabled=${this.contributionBusy}>
      <legend>Contribution notes</legend>
      <div class="metadata-group-body">
        <p class="metadata-group-description">Optional context for reviewers; this is not added to model.json.</p>
        ${this.renderTextarea("notes", "Notes", draft.notes)}
      </div>
    </fieldset>`;
  }

  private renderTextarea(name: "measure_description" | "notes", label: string, value: unknown) {
    const error = this.fieldError(name);
    const labelId = `${name}-label`;
    const errorId = `${name}-error`;
    return html`<label class="notes-field">
      <span id=${labelId}>${label}</span>
      <textarea name=${name} .value=${this.fieldValue(name, value)} aria-labelledby=${labelId}
        aria-invalid=${error ? "true" : "false"} aria-describedby=${error ? errorId : nothing}></textarea>
      ${this.renderFieldError(name)}
    </label>`;
  }

  private renderValidationFooter() {
    const valid = this.canContinue();
    let statusClass = "validation-status";
    if (valid) statusClass += " valid";
    else if (this.previewDirty) statusClass += " pending";
    return html`<div class="validation-footer">
      <p class=${statusClass} role="status">${this.validationStatus(valid)}</p>
      ${valid ? this.renderContinueButton() : this.renderValidateButton()}
    </div>`;
  }

  private validationStatus(valid: boolean) {
    if (valid) return html`<span aria-hidden="true">✓</span> Profile validated`;
    if (this.contributionBusy) return "Checking your metadata and generated profile…";
    if (this.contributionError || Object.keys(this.fieldErrors).length) {
      return "Review the validation errors above, then validate again.";
    }
    return this.previewDirty ? "Your changes have not been validated yet." : "Validate your metadata before continuing.";
  }

  private renderContinueButton() {
    return html`<button class="primary" type="button" @click=${() => { if (this.canContinue()) emit(this, "share"); }}>Continue to use profile</button>`;
  }

  private renderValidateButton() {
    let label = "Validate profile";
    if (this.contributionBusy) label = "Validating profile…";
    else if (this.previewDirty) label = "Validate changes";
    return html`<button class="primary" type="submit" ?disabled=${this.contributionBusy}>${label}</button>`;
  }

  private renderMeasurementContext(draft: ContributionDraft) {
    const entries = Object.entries(draft.home_assistant).filter(([, value]) => value !== null && value !== "");
    if (!entries.length) return nothing;
    return html`
      <details class="profile-details">
        <summary>Measurement context</summary>
        <div class="profile-details-body">
          <dl class="info-list" aria-label="Home Assistant measurement context">
            ${entries.map(([label, value]) => html`<div><dt><span>Home Assistant ${words(label)}</span></dt><dd>${value}</dd></div>`)}
          </dl>
        </div>
      </details>`;
  }

  private renderMainsVoltage(draft: ContributionDraft) {
    if (draft.voltage_range) {
      return html`
        <label>
          <span>Nominal mains voltage</span>
          <input type="text" .value=${`${draft.mains_voltage ?? "—"} V`} readonly />
          <small class="field-hint">Calculated from the measured ${draft.voltage_range.min}–${draft.voltage_range.max} V range.</small>
        </label>`;
    }
    return html`
      <measure-combobox
        name="mains_voltage"
        label="Nominal mains voltage"
        .value=${this.fieldValue("mains_voltage", draft.mains_voltage)}
        .options=${[120, 230].map((voltage) => ({ value: String(voltage), label: `${voltage} V` }))}
        .error=${this.fieldError("mains_voltage")}
        ?disabled=${this.contributionBusy}
        placeholder="Select voltage"
        hint="The power meter did not report a voltage range, so select the nominal mains voltage used during measurement."
        required
      ></measure-combobox>`;
  }

  private renderDeviceSpecifications(draft: ContributionDraft) {
    const deviceType = this.deviceType(draft);
    let fields: DeviceSpecificationField[] = [];
    if (deviceType) fields = this.deviceSpecificationFields[deviceType] ?? [];
    const typeLabel = deviceType ? optionLabel(deviceType) : "this device type";
    return html`
      <fieldset class="metadata-group" ?disabled=${this.contributionBusy}>
        <legend>Device specifications</legend>
        <div class="metadata-group-body">
          <p class="metadata-group-description">Optional manufacturer specifications for ${typeLabel.toLowerCase()} profiles.</p>
          ${fields.length
            ? html`<div class="contribution-grid">${fields.map((field) => this.renderDeviceSpecification(field, draft.device_specs?.[field.name]))}</div>`
            : html`<p class="muted">Specification fields are currently unavailable. Existing values will be kept.</p>`}
          ${this.renderFieldError("device_specs")}
        </div>
      </fieldset>`;
  }

  private renderDeviceSpecification(field: DeviceSpecificationField, value: unknown) {
    const name = `device_specs.${field.name}`;
    const error = this.fieldError(name);
    if (field.collection !== "scalar") return this.renderSpecificationCollection(field, name, value, error);
    if (field.value_type === "boolean" || field.options.length) return this.renderSpecificationChoice(field, name, value, error);
    return this.renderSpecificationInput(field, name, value, error);
  }

  private renderSpecificationCollection(field: DeviceSpecificationField, name: string, value: unknown, error: string) {
    const selected = specificationValues(value);
    return html`<measure-combobox name=${name} label=${field.label} .error=${error}
      ?disabled=${this.contributionBusy}
      .value=${guard([value, this.contributionFormValues[name]], () => this.contributionFormValues[name] ?? selected)}
      .options=${field.options.map((option) => ({ value: option, label: optionLabel(option) }))}
      placeholder="Select an option…" hint=${field.description} multiple></measure-combobox>`;
  }

  private renderSpecificationChoice(field: DeviceSpecificationField, name: string, value: unknown, error: string) {
    const values = field.value_type === "boolean" ? ["true", "false"] : field.options;
    const options = values.map((option) => ({ value: option, label: specificationOptionLabel(field, option) }));
    return html`<measure-combobox name=${name} label=${field.label}
      .value=${this.fieldValue(name, value)}
      .options=${[{ value: "", label: "Not specified" }, ...options]}
      .error=${error} ?disabled=${this.contributionBusy}
      placeholder="Not specified" hint=${field.description}></measure-combobox>`;
  }

  private renderSpecificationInput(field: DeviceSpecificationField, name: string, value: unknown, error: string) {
    const labelId = `${name}-label`;
    const hintId = `${name}-hint`;
    const errorId = `${name}-error`;
    const describedBy = [field.description ? hintId : "", error ? errorId : ""].filter(Boolean).join(" ");
    const numeric = field.value_type === "number" || field.value_type === "integer";
    const label = specificationInputLabel(field);
    let step: string | typeof nothing = nothing;
    if (field.value_type === "integer") step = "1";
    else if (field.value_type === "number") step = "any";
    return html`
      <label>
        <span id=${labelId}>${label}</span>
        <input
          name=${name}
          aria-labelledby=${labelId}
          aria-invalid=${error ? "true" : "false"}
          aria-describedby=${describedBy || nothing}
          type=${numeric ? "number" : "text"}
          step=${step}
          .value=${this.fieldValue(name, value)}
        />
        ${field.description ? html`<small id=${hintId} class="field-hint">${field.description}</small>` : nothing}
        ${this.renderFieldError(name)}
      </label>`;
  }

  private renderPreparedPreview(preview: ContributionPreview) {
    const files = preview.files.map((file) => formatPreparedFile(file)).join("\n");
    const model = preview.model_json ?? preview.files.find((file) => file.path.endsWith("model.json"))?.rendered_json ?? {};
    return html`
      ${preview.warnings.map((warning) => html`<p class="notice warning preparation-warning">${warning}</p>`)}
      <details class="profile-details prepared-preview">
        <summary>Prepared files (${preview.files.length})</summary>
        <div class="profile-details-body">
          <div class="preview-block"><span>Files</span><pre>${files}</pre></div>
          <div class="preview-block"><span>Generated model.json</span><pre>${JSON.stringify(model, null, 2)}</pre></div>
        </div>
      </details>`;
  }

  private input(
    name: keyof ContributionPreviewRequest,
    label: string,
    value: string,
    options: { required?: boolean; placeholder?: string; hint?: string; error?: string } = {},
  ) {
    const { required = true, placeholder = "", hint = "" } = options;
    const error = options.error ?? this.fieldError(name);
    const labelId = `${name}-label`;
    const hintId = `${name}-hint`;
    const errorId = `${name}-error`;
    const requiredMarker = required ? html` <span class="required-marker" aria-hidden="true">*</span>` : nothing;
    const hintMarkup = hint ? html`<small id=${hintId} class="field-hint">${hint}</small>` : nothing;
    const errorMarkup = error ? html`<small id=${errorId} class="field-hint error">${error}</small>` : nothing;
    const describedBy = [hint ? hintId : "", error ? errorId : ""].filter(Boolean).join(" ");
    return html`
      <label>
        <span id=${labelId}>${label}${requiredMarker}</span>
        <input name=${name} type=${name === "contributor_email" ? "email" : "text"} .value=${this.fieldValue(name, value)} ?required=${required} placeholder=${placeholder} autocomplete="off" aria-invalid=${error ? "true" : "false"}
          aria-labelledby=${labelId}
          aria-describedby=${describedBy || nothing} />
        ${hintMarkup}
        ${errorMarkup}
      </label>`;
  }

  private collectContribution(): ContributionPreviewRequest | null {
    const form = this.shadowRoot?.querySelector<HTMLFormElement>(".contribution-form");
    if (!form) return null;
    const data = new FormData(form);
    const draft = this.editableDraft();
    let fields: DeviceSpecificationField[] = [];
    if (draft) fields = this.deviceSpecificationFields[this.deviceType(draft)] ?? [];
    const deviceSpecs = fields.length ? collectDeviceSpecifications(form, data, fields) : draft?.device_specs ?? null;
    const mainsVoltageControl = form.querySelector('measure-combobox[name="mains_voltage"]') as (HTMLElement & { value?: string }) | null;
    const mainsVoltageValue = contributionMainsVoltage(data, mainsVoltageControl, draft);
    return {
      manufacturer_name: formText(data, "manufacturer_name"),
      model_id: formText(data, "model_id"),
      product_name: formText(data, "product_name"),
      contributor: formText(data, "contributor"),
      contributor_github: formText(data, "contributor_github"),
      contributor_email: formText(data, "contributor_email"),
      aliases: formList(data, "aliases"),
      gtins: formList(data, "gtins"),
      product_url: formText(data, "product_url"),
      mains_voltage: mainsVoltageValue ? Number(mainsVoltageValue) : null,
      device_specs: deviceSpecs,
      measure_device: formText(data, "measure_device"),
      measure_device_firmware: formText(data, "measure_device_firmware"),
      measure_description: formText(data, "measure_description"),
      notes: formText(data, "notes"),
    };
  }

  private previewContribution(event: SubmitEvent): void {
    event.preventDefault();
    if (this.contributionBusy) return;
    const detail = this.collectContribution();
    if (!detail) return;
    this.contributionEdit = detail;
    this.fieldErrors = validateMetadata(detail);
    const form = this.shadowRoot?.querySelector(".contribution-form");
    for (const input of form?.querySelectorAll<HTMLInputElement>('input[type="number"]') ?? []) {
      if (!input.validity.valid) this.fieldErrors[input.name] = input.validity.badInput ? "Enter a number." : "Enter a whole number.";
    }
    if (Object.keys(this.fieldErrors).length) {
      this.previewDirty = true;
      void this.updateComplete.then(() => this.focusValidation());
      return;
    }
    emit<ContributionPreviewRequest>(this, "contribution-preview", detail);
  }

  private fieldError(name: string): string {
    const clientError = this.fieldErrors[name];
    if (clientError) return clientError;
    if (this.contributionErrorField === name && this.dismissedServerField !== name) return this.contributionError;
    return "";
  }

  private renderFieldError(name: string) {
    const error = this.fieldError(name);
    if (!error) return nothing;
    return html`<small id=${`${name}-error`} class="field-hint error">${error}</small>`;
  }

  private validationErrors(): Record<string, string> {
    const errors = { ...this.fieldErrors };
    if (this.contributionError && this.dismissedServerField !== this.contributionErrorField) {
      errors[this.contributionErrorField ?? ""] = this.contributionError;
    } else if (this.contributionError && !this.contributionErrorField) errors[""] = this.contributionError;
    return errors;
  }

  private renderValidationSummary() {
    const errors = Object.entries(this.validationErrors());
    if (!errors.length) return nothing;
    return html`<div class="notice error validation-summary" role="alert" tabindex="-1">
      <strong>Check these profile details:</strong>
      <ul>${errors.map(([name, message]) => this.renderValidationError(name, message))}</ul>
    </div>`;
  }

  private renderValidationError(name: string, message: string) {
    const knownSpec = Object.values(this.deviceSpecificationFields).flat().some((field) => name === `device_specs.${field.name}`);
    const focusable = (name in metadataLabels && name !== "device_specs") || knownSpec;
    const content = focusable
      ? html`<button type="button" @click=${() => this.focusField(name)}>${this.fieldLabel(name)}: ${message}</button>`
      : message;
    return html`<li>${content}</li>`;
  }

  private fieldLabel(name: string): string {
    const spec = Object.values(this.deviceSpecificationFields).flat().find((field) => `device_specs.${field.name}` === name);
    return metadataLabels[name] ?? spec?.label ?? words(name);
  }

  private fieldControl(name: string): HTMLElement | undefined {
    return Array.from(this.shadowRoot?.querySelectorAll<HTMLElement>("[name]") ?? [])
      .find((control) => control.getAttribute("name") === name && control.getAttribute("type") !== "hidden");
  }

  private focusField(name: string): void {
    const control = this.fieldControl(name);
    const input = control?.shadowRoot?.querySelector<HTMLElement>("input, select") ?? control;
    input?.focus();
    input?.scrollIntoView?.({ block: "center", behavior: "smooth" });
  }

  private focusValidation(): void {
    const first = Object.keys(this.validationErrors()).find((name) => this.fieldControl(name));
    if (first) this.focusField(first);
    else {
      const summary = this.shadowRoot?.querySelector<HTMLElement>(".validation-summary");
      summary?.focus();
      summary?.scrollIntoView?.({ block: "center" });
    }
  }

  private metadataChanged(event: Event): void {
    const control = event.target as HTMLElement & { name?: string; value?: string | string[] };
    const name = control.name;
    if (!name || name === "confirm_contribution") return;
    if (control.value !== undefined) {
      this.contributionFormValues = { ...this.contributionFormValues, [name]: control.value };
      emit(this, "contribution-edit", this.contributionFormValues);
    }
    this.previewDirty = true;
    const errors = { ...this.fieldErrors };
    delete errors[name];
    this.fieldErrors = errors;
    if (this.contributionErrorField === name) this.dismissedServerField = name;
  }

  private fieldValue(name: string, fallback: unknown): string {
    return formValue(this.contributionFormValues[name] ?? fallback);
  }

  private validateField(event: FocusEvent): void {
    const control = event.target as HTMLElement & { name?: string };
    const name = control.name;
    if (!name || this.contributionBusy || event.relatedTarget === control || control.contains(event.relatedTarget as Node | null)) return;
    const values = this.collectContribution();
    if (!values) return;
    const validation = validateMetadata(values);
    const errors = { ...this.fieldErrors };
    for (const field of name === "manufacturer_name" ? [name, "product_name"] : [name]) {
      if (validation[field]) errors[field] = validation[field];
      else delete errors[field];
    }
    this.fieldErrors = errors;
  }

  private canContinue(): boolean {
    return Boolean(this.contributionPreview && !this.previewDirty && !this.contributionBusy && !this.contributionError && !Object.keys(this.fieldErrors).length);
  }

  private editableDraft(): ContributionDraft | undefined {
    const source = this.contributionPreview ?? this.contributionDraft;
    return source && this.contributionEdit ? { ...source, ...this.contributionEdit } : source;
  }

  private deviceType(draft: ContributionDraft): string {
    if (draft.device_type) return draft.device_type;
    if (typeof draft.model_json !== "object" || draft.model_json === null || Array.isArray(draft.model_json)) return "";
    const value = (draft.model_json as Record<string, unknown>).device_type;
    return typeof value === "string" ? value : "";
  }
}

function formList(data: FormData, name: string): string[] {
  return formText(data, name).split(",").map((value) => value.trim()).filter(Boolean);
}

function collectDeviceSpecifications(form: HTMLFormElement, data: FormData, fields: DeviceSpecificationField[]): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const field of fields) {
    const name = `device_specs.${field.name}`;
    if (field.collection !== "scalar") {
      collectSpecificationCollection(result, form, data, field, name);
      continue;
    }
    collectScalarSpecification(result, form, data, field, name);
  }
  return result;
}

function collectSpecificationCollection(
  result: Record<string, unknown>,
  form: HTMLFormElement,
  data: FormData,
  field: DeviceSpecificationField,
  name: string,
): void {
  const control = Array.from(form.querySelectorAll("measure-combobox"))
    .find((candidate) => candidate.multiple && candidate.name === name);
  const controlValues = Array.isArray(control?.value) ? control.value : [];
  const submitted = data.getAll(name).map(String);
  const values = (submitted.length ? submitted : controlValues).filter(Boolean);
  if (!values.length) return;
  result[field.name] = field.collection === "scalar_or_array" && values.length === 1 ? values[0] : values;
}

function collectScalarSpecification(
  result: Record<string, unknown>,
  form: HTMLFormElement,
  data: FormData,
  field: DeviceSpecificationField,
  name: string,
): void {
  const control = Array.from(form.querySelectorAll("measure-combobox"))
    .find((candidate) => !candidate.multiple && candidate.name === name);
  const controlValue = typeof control?.value === "string" ? control.value : "";
  const value = formText(data, name) || controlValue;
  if (!value) return;
  if (field.value_type === "number" || field.value_type === "integer") result[field.name] = Number(value);
  else if (field.value_type === "boolean") result[field.name] = value === "true";
  else result[field.name] = value;
}

function specificationValues(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String);
  if (value === undefined || value === null) return [];
  return [formValue(value)];
}

function specificationOptionLabel(field: DeviceSpecificationField, option: string): string {
  if (field.value_type !== "boolean") return optionLabel(option);
  return option === "true" ? "Yes" : "No";
}

function specificationInputLabel(field: DeviceSpecificationField): string {
  if (field.name === "rated_power") return "Rated power (W)";
  if (field.name === "lumens") return "Light output (lm)";
  return field.label;
}

function contributionMainsVoltage(
  data: FormData,
  control: (HTMLElement & { value?: string }) | null,
  draft: ContributionDraft | undefined,
): string {
  const submitted = formText(data, "mains_voltage");
  if (submitted) return submitted;
  if (typeof control?.value === "string" && control.value) return control.value;
  return formValue(draft?.mains_voltage);
}

function formValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function formatPreparedFile(file: ContributionDraftFile): string {
  return file.size === undefined ? file.path : `${file.path} (${fileSize(file.size)})`;
}

function optionLabel(value: string): string {
  const abbreviations: Record<string, string> = {
    rf433: "RF 433",
    usb: "USB",
    wifi: "Wi-Fi",
    zwave: "Z-Wave",
  };
  if (abbreviations[value]) return abbreviations[value];
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
