import { css, html, nothing } from "lit";
import type { EntityDescriptor, FormField } from "../types";
import { entityOption, fieldHint } from "./fields";

/**
 * Several entities measured together, as a growable list of selects. Every row submits under the
 * same field name, so the surrounding form reads them back with `getAll` — which is also why this
 * renders into that form's own tree instead of being a custom element with its own shadow root.
 */

export interface EntityListOptions {
  field: FormField;
  entities: EntityDescriptor[];
  /** One entry per select, empty string included — an unanswered select is still a row. */
  rows: string[];
  onChange: (rows: string[]) => void;
}

export const entityListStyles = css`
  .entity-list { display: grid; gap: 0.4rem; }
  .entity-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.5rem; align-items: center; }
  .entity-row button, .add-entity { min-height: 40px; }
  .remove-entity { display: grid; place-items: center; width: 44px; padding: 0; }
  .remove-entity svg { width: 20px; height: 20px; }
`;

export function renderEntityList({ field, entities, rows, onChange }: EntityListOptions) {
  const values = rows.length ? rows : [""];
  const rowChanged = (index: number, event: Event) => {
    const updated = [...values];
    updated[index] = (event.currentTarget as HTMLSelectElement).value;
    onChange(updated);
  };
  return html`<div class="entity-list">
    <span class="field-label">${field.plural_label || field.label}</span>
    ${values.map((value, index) => html`<div class="entity-row">
      <select name=${field.name} required @change=${(event: Event) => rowChanged(index, event)}>
        <option value="">Select an entity</option>
        ${entities.map((entity) => entityOption(
          entity,
          entity.entity_id === value,
          // An entity already measured in another row cannot be picked twice.
          entity.entity_id !== value && values.includes(entity.entity_id),
        ))}
      </select>
      ${values.length > 1 ? renderRemove(field, values, index, onChange) : nothing}
    </div>`)}
    <button class="add-entity" type="button" @click=${() => onChange([...values, ""])}>
      Add another ${field.label.toLowerCase()}
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
