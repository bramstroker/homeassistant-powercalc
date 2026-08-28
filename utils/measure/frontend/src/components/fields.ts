import { html, nothing } from "lit";
import type { EntityDescriptor } from "../types";
import type { ComboboxOption } from "./combobox";
import "./combobox";

/**
 * Form controls shared by the views that render inputs. They are plain functions rather than a
 * base class so any view can compose them, and they carry no state of their own — the caller
 * supplies the current value and receives the change through the form or an explicit handler.
 */

export interface TextFieldOptions {
  value?: string;
  placeholder?: string;
  required?: boolean;
  hint?: string;
}

export function textField(name: string, label: string, options: TextFieldOptions = {}) {
  const { value = "", placeholder = "", required = false, hint = "" } = options;
  return html`<label>
    <span>${label}</span>
    <input name=${name} .value=${value} placeholder=${placeholder} ?required=${required} autocomplete="off" />
    ${fieldHint(hint)}
  </label>`;
}

export interface NumberFieldOptions {
  min?: number;
  max?: number;
  step?: string;
  hint?: string;
  required?: boolean;
  disabled?: boolean;
  onInput?: ((event: Event) => void) | null;
}

export function numberField(name: string, label: string, value: string, options: NumberFieldOptions = {}) {
  const { min, max, step = "1", hint = "", required = true, disabled = false, onInput = null } = options;
  return html`<label>
    <span>${label}</span>
    <input
      type="number"
      name=${name}
      min=${min ?? nothing}
      max=${max ?? nothing}
      step=${step}
      .value=${value}
      ?required=${required}
      ?disabled=${disabled}
      @input=${onInput}
    />
    ${fieldHint(hint)}
  </label>`;
}

export interface EntitySelectOptions {
  selected?: string;
  required?: boolean;
  onChange?: ((event: Event) => void) | null;
}

export function entitySelect(name: string, label: string, entities: EntityDescriptor[], options: EntitySelectOptions = {}) {
  const { selected = "", required = false, onChange = null } = options;
  const comboboxOptions: ComboboxOption[] = entities.map((entity) => ({
    value: entity.entity_id,
    label: `${entity.name} · ${entity.entity_id}`,
  }));
  if (!required) comboboxOptions.unshift({ value: "", label: "None" });
  return html`
    <measure-combobox
      name=${name}
      label=${label}
      .value=${selected}
      .options=${comboboxOptions}
      placeholder=${`Search ${label.toLowerCase()} entities`}
      ?required=${required}
    >
      <input slot="value" type="hidden" name=${name} .value=${selected} @change=${onChange} />
    </measure-combobox>
  `;
}

export function entityOption(entity: EntityDescriptor, selected: boolean, disabled = false) {
  return html`<option value=${entity.entity_id} ?selected=${selected} ?disabled=${disabled}>
    ${entity.name} · ${entity.entity_id}
  </option>`;
}

export function fieldHint(hint: string) {
  return hint ? html`<small class="field-hint">${hint}</small>` : nothing;
}
