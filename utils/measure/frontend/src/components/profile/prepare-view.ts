import { LitElement, css, html, nothing } from "lit";
import type { PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type {
  ContributionAuthState,
  ContributionDraft,
  ContributionFormValues,
  ContributionPreview,
  ContributionPreviewRequest,
  DeviceSpecificationField,
  SessionSnapshot,
} from "../../types";
import { emit } from "../../events";
import { words } from "../../format";
import { formText } from "../../form";
import { metadataLabels, validateMetadata } from "../../profile-validation";
import { sharedStyles } from "../../styles";
import { profileDeviceType } from "./device-specification-fields";
import { formValue, type ProfileFormSection } from "./form-section";
import "./contribution-details";
import "./contributor-fields";
import "./device-specification-fields";
import "./measurement-fields";
import "./prepared-preview";
import "./product-fields";

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
    if (changed.has("contributionError") && this.contributionError) void this.focusValidationAfterRender();
  }

  static readonly styles = [sharedStyles, css`
    .profile-guidance { max-width: 1000px; line-height: 1.55; }
    .manufacturer-library-link { white-space: nowrap; }
    .contribution { margin-top: 1.5rem; }
    .profile-metadata { padding: 0; border: 0; border-radius: 0; background: transparent; }
    .contribution-auto { padding: clamp(0.85rem, 3vw, 1.2rem); border: 1px solid var(--line); border-radius: 12px; background: color-mix(in srgb, var(--field) 68%, transparent); }
    .contribution-form { display: grid; }
    measure-profile-product-fields,
    measure-profile-contributor-fields,
    measure-profile-measurement-fields,
    measure-profile-device-specification-fields,
    measure-profile-contribution-details,
    measure-profile-prepared-preview { display: contents; }
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
    const errors = this.validationErrors();
    return html`
      <div class="contribution-auto">
        <form class="contribution-form" novalidate @submit=${this.previewContribution}
          @input=${this.metadataChanged} @change=${this.metadataChanged}
          @focusout=${this.validateField}
          @combobox-change=${this.metadataChanged}>
          ${this.renderValidationSummary()}
          <p class="muted required-guidance">Fields marked <span class="required-marker" aria-hidden="true">*</span><span class="sr-only">with an asterisk</span> are required.</p>
          <measure-profile-product-fields
            .draft=${draft} .values=${this.contributionFormValues} .errors=${errors}
            .busy=${this.contributionBusy} .manufacturers=${this.manufacturers}
          ></measure-profile-product-fields>
          <measure-profile-contributor-fields
            .draft=${draft} .values=${this.contributionFormValues} .errors=${errors}
            .busy=${this.contributionBusy} .contributionAuth=${this.contributionAuth}
          ></measure-profile-contributor-fields>
          <measure-profile-measurement-fields
            .draft=${draft} .values=${this.contributionFormValues} .errors=${errors}
            .busy=${this.contributionBusy} .measureDevices=${this.measureDevices}
            .measureDevicesLoading=${this.measureDevicesLoading} .measureDevicesError=${this.measureDevicesError}
          ></measure-profile-measurement-fields>
          <measure-profile-device-specification-fields
            .draft=${draft} .values=${this.contributionFormValues} .errors=${errors}
            .busy=${this.contributionBusy} .specificationFields=${this.deviceSpecificationFields}
          ></measure-profile-device-specification-fields>
          <measure-profile-contribution-details
            .draft=${draft} .values=${this.contributionFormValues} .errors=${errors} .busy=${this.contributionBusy}
          ></measure-profile-contribution-details>
          ${this.renderValidationFooter()}
        </form>
        ${this.contributionPreview && this.canContinue()
          ? html`<measure-profile-prepared-preview .preview=${this.contributionPreview}></measure-profile-prepared-preview>`
          : nothing}
      </div>`;
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


  private collectContribution(): ContributionPreviewRequest | null {
    const form = this.shadowRoot?.querySelector<HTMLFormElement>(".contribution-form");
    if (!form) return null;
    const data = new FormData(form);
    const draft = this.editableDraft();
    let fields: DeviceSpecificationField[] = [];
    if (draft) fields = this.deviceSpecificationFields[profileDeviceType(draft)] ?? [];
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
      void this.focusValidationAfterRender();
      return;
    }
    emit<ContributionPreviewRequest>(this, "contribution-preview", detail);
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

  private async focusValidationAfterRender(): Promise<void> {
    await this.updateComplete;
    const sections = this.shadowRoot?.querySelectorAll<ProfileFormSection>(
      "measure-profile-product-fields, measure-profile-contributor-fields, measure-profile-measurement-fields, measure-profile-device-specification-fields",
    ) ?? [];
    await Promise.all(Array.from(sections, (section) => section.updateComplete));
    this.focusValidation();
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
