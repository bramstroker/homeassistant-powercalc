import { html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { guard } from "lit/directives/guard.js";
import type { ContributionDraft, DeviceSpecificationField } from "../../types";
import { formValue, ProfileFormSection } from "./form-section";
import "../shared/combobox";

@customElement("measure-profile-device-specification-fields")
export class ProfileDeviceSpecificationFields extends ProfileFormSection {
  @property({ attribute: false }) specificationFields: Record<string, DeviceSpecificationField[]> = {};

  render() {
    const deviceType = profileDeviceType(this.draft);
    const fields = deviceType ? this.specificationFields[deviceType] ?? [] : [];
    const typeLabel = deviceType ? optionLabel(deviceType) : "this device type";
    return html`
      <fieldset class="metadata-group" ?disabled=${this.busy}>
        <legend>Device specifications</legend>
        <div class="metadata-group-body">
          <p class="metadata-group-description">Optional manufacturer specifications for ${typeLabel.toLowerCase()} profiles.</p>
          ${fields.length
            ? html`<div class="contribution-grid">${fields.map((field) => this.renderSpecification(field))}</div>`
            : html`<p class="muted">Specification fields are currently unavailable. Existing values will be kept.</p>`}
          ${this.renderFieldError("device_specs")}
        </div>
      </fieldset>`;
  }

  private renderSpecification(field: DeviceSpecificationField) {
    const name = `device_specs.${field.name}`;
    const value = this.draft.device_specs?.[field.name];
    const error = this.fieldError(name);
    if (field.collection !== "scalar") return this.renderCollection(field, name, value, error);
    if (field.value_type === "boolean" || field.options.length) return this.renderChoice(field, name, value, error);
    return this.renderSpecificationInput(field, name, value, error);
  }

  private renderCollection(field: DeviceSpecificationField, name: string, value: unknown, error: string) {
    const selected = specificationValues(value);
    return html`<measure-combobox
      name=${name}
      label=${field.label}
      .error=${error}
      ?disabled=${this.busy}
      .value=${guard([value, this.values[name]], () => this.values[name] ?? selected)}
      .options=${field.options.map((option) => ({ value: option, label: optionLabel(option) }))}
      placeholder="Select an option…"
      hint=${field.description}
      multiple
    ></measure-combobox>`;
  }

  private renderChoice(field: DeviceSpecificationField, name: string, value: unknown, error: string) {
    const values = field.value_type === "boolean" ? ["true", "false"] : field.options;
    const options = values.map((option) => ({ value: option, label: specificationOptionLabel(field, option) }));
    return html`<measure-combobox
      name=${name}
      label=${field.label}
      .value=${this.fieldValue(name, value)}
      .options=${[{ value: "", label: "Not specified" }, ...options]}
      .error=${error}
      ?disabled=${this.busy}
      placeholder="Not specified"
      hint=${field.description}
    ></measure-combobox>`;
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
}

export function profileDeviceType(draft: ContributionDraft): string {
  if (draft.device_type) return draft.device_type;
  if (typeof draft.model_json !== "object" || draft.model_json === null || Array.isArray(draft.model_json)) return "";
  const value = (draft.model_json as Record<string, unknown>).device_type;
  return typeof value === "string" ? value : "";
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
