import { css, html, nothing } from "lit";
import type { EntityDescriptor, FormField } from "../types";
import type { ComboboxOption } from "./combobox";
import "./combobox";
import { fieldHint } from "./fields";

/**
 * Several entities measured together, as a growable list of searchable comboboxes. Every row
 * submits under the same field name, so the surrounding form reads them back with `getAll`.
 */

export interface EntityListOptions {
  field: FormField;
  entities: EntityDescriptor[];
  /** One entry per picker, empty string included — an unanswered picker is still a row. */
  rows: string[];
  onChange: (rows: string[]) => void;
}

export const entityListStyles = css`
  .entity-list { display: grid; gap: 0.65rem; }
  .entity-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.5rem; align-items: end; }
  .entity-row button { min-height: 40px; }
  .add-entity { justify-self: start; width: auto; min-height: 36px; padding: 0.45rem 0.75rem; font-size: 0.82rem; }
  .remove-entity { display: grid; place-items: center; width: 44px; padding: 0; }
  .remove-entity svg { width: 20px; height: 20px; }
`;

export function renderEntityList({ field, entities, rows, onChange }: EntityListOptions) {
  const values = rows.length || !field.required ? rows : [""];
  const rowChanged = (index: number, event: Event) => {
    const updated = [...values];
    updated[index] = (event.currentTarget as HTMLInputElement).value;
    onChange(updated);
  };
  return html`<div class="entity-list">
    ${values.length ? nothing : html`<span class="field-label">${field.plural_label || field.label}</span>`}
    ${values.map((value, index) => {
      const options: ComboboxOption[] = entities.map((entity) => ({
        value: entity.entity_id,
        label: `${entity.name} · ${entity.entity_id}`,
        // An entity already measured in another row cannot be picked twice.
        disabled: entity.entity_id !== value && values.includes(entity.entity_id),
      }));
      return html`<div class="entity-row">
        <measure-combobox
          name=${field.name}
          .value=${value}
          label=${values.length > 1 ? `${field.label} ${index + 1}` : field.plural_label || field.label}
          .options=${options}
          placeholder=${`Search ${field.label.toLowerCase()} entities`}
          ?required=${field.required}
        >
          <input
            slot="value"
            type="hidden"
            name=${field.name}
            .value=${value}
            @change=${(event: Event) => rowChanged(index, event)}
          />
        </measure-combobox>
        ${values.length > 1 ? renderRemove(field, values, index, onChange) : nothing}
      </div>`;
    })}
    <button class="add-entity" type="button" @click=${() => onChange([...values, ""])}>
      ${values.length ? "Add another" : "Add"} ${field.label.toLowerCase()}
    </button>
    ${fieldHint(field.hint ?? "")}
  </div>`;
}

function renderRemove(field: FormField, values: string[], index: number, onChange: (rows: string[]) => void) {
  return html`<button
    class="remove-entity danger"
    type="button"
    aria-label="Remove ${field.label}"
    title="Remove ${field.label}"
    @click=${() => onChange(values.filter((_, position) => position !== index))}
  >
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 10v6M14 10v6"></path>
    </svg>
  </button>`;
}
