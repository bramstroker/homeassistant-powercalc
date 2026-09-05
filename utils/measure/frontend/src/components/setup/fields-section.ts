import { LitElement, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type {
  Capabilities,
  EntityDescriptor,
  FormField,
  FormFieldOption,
  MeasureDefinition,
  MeasureParameterName,
  MeasurementRequest,
} from "../../types";
import {
  deviceFields,
  entityDomain,
  entityDomains,
  narrowingField,
  requestFieldValue,
} from "../../measure-definition";
import { emit } from "../../events";
import { entitySelect, fieldHint, optionSelect, textField } from "../shared/fields";
import { renderEntityList } from "./entity-list-field";
import {
  activeParameters,
  availableOptions,
  entityChoices,
  entityRows,
  recorderExportFilename,
  recorderPurpose,
  selectedEntityId,
  selectedEntityIds,
  selectedOptions,
  selectValue,
  visible,
  type FieldState,
} from "./options";
import "./tuning-section";

const LIGHT_DISCOVERY_HINT =
  "Newly discovered lights may not have a usable state until Home Assistant receives their first update. If a light is missing, change its state once in Home Assistant, then reload this page.";
const MULTIPLE_LIGHTS_GUIDE_URL = "https://docs.powercalc.nl/contributing/measure/lights/#multiple-identical-lights";
const HOME_ASSISTANT_GROUP_GUIDE_URL = "https://www.home-assistant.io/integrations/group/";

export interface EntitySelectionChange {
  name: string;
  rows: string[];
}

export interface SelectValueChange {
  name: string;
  value: string;
}

export interface MultiSelectionChange {
  name: string;
  values: string[];
}

export interface MultipleLightsChange {
  checked: boolean;
  fieldName: string;
}

@customElement("measure-setup-fields-section")
export class SetupFieldsSection extends LitElement {
  @property({ attribute: false }) capabilities?: Capabilities;
  @property({ attribute: false }) definition?: MeasureDefinition;
  @property({ attribute: false }) definitions: MeasureDefinition[] = [];
  @property({ attribute: false }) request?: MeasurementRequest;
  @property({ attribute: false }) lights: EntityDescriptor[] = [];
  @property({ attribute: false }) deviceEntities: Record<string, EntityDescriptor[]> = {};
  @property({ attribute: false }) deviceEntityErrors: Record<string, string> = {};
  @property({ attribute: false }) selectedEntities: Record<string, string[]> = {};
  @property({ attribute: false }) selectValues: Record<string, string> = {};
  @property({ attribute: false }) multiSelection: Record<string, string[]> = {};
  @property({ attribute: false }) parameterValues: Partial<Record<MeasureParameterName, string>> = {};
  @property({ type: Boolean }) dummyController = false;
  @property({ type: Boolean }) multipleLights = false;
  @property({ type: String }) derivedCountOverride?: string;

  private get fieldState(): FieldState | undefined {
    if (!this.definition) return undefined;
    return {
      definition: this.definition,
      request: this.request,
      lights: this.lights,
      deviceEntities: this.deviceEntities,
      selectedEntities: this.selectedEntities,
      selectValues: this.selectValues,
      multiSelection: this.multiSelection,
      dummyController: this.dummyController,
    };
  }

  protected createRenderRoot(): HTMLElement | DocumentFragment {
    return this;
  }

  protected async getUpdateComplete(): Promise<boolean> {
    const complete = await super.getUpdateComplete();
    const tuning = this.querySelector<LitElement>("measure-setup-tuning-section");
    await tuning?.updateComplete;
    return complete;
  }

  render() {
    const definition = this.definition;
    const capabilities = this.capabilities;
    if (!definition || !capabilities) return html`<p class="muted">Loading measurement capabilities…</p>`;
    const fields = deviceFields(definition);
    const multipleController = fields.find((field) => field.role === "controller" && field.multiple);
    const blocks = fields.filter((field) => field.control === "multi_select" && visible(field, this.fieldState!));
    return html`
      <div class="device-section">
        ${this.dummyController ? html`<p class="test-mode-status" role="status">Virtual device · test output only</p>` : nothing}
        ${multipleController && !this.dummyController ? this.renderMultipleLightsToggle(multipleController) : nothing}
        <div class="field-with-help">
          <div class="grid profile-grid ${definition.measure_type === "light" ? "light-grid" : ""}">
            ${fields.filter((field) => field.control !== "multi_select").map((field) => this.renderField(field))}
            ${this.dummyController || !definition.fields.some((field) => field.role === "controller")
              ? textField("session_name", "Session name (optional)", {
                  value: this.request?.session_name ?? "",
                  placeholder: "e.g. Desk lamp test",
                  hint: "A label for finding this measurement later; it is not the product name.",
                })
              : nothing}
          </div>
          ${definition.measure_type === "light" && !this.dummyController
            ? this.contextHelp("Light not found?", html`<p>${LIGHT_DISCOVERY_HINT}</p>`, "discovery-help")
            : nothing}
        </div>
        ${blocks.map((field) => this.renderMultiSelect(field))}
      </div>
      <measure-setup-tuning-section
        .capabilities=${capabilities}
        .definition=${definition}
        .definitions=${this.definitions}
        .request=${this.request}
        .values=${this.parameterValues}
        .activeParameters=${activeParameters(this.fieldState!)}
      ></measure-setup-tuning-section>
    `;
  }

  private renderMultipleLightsToggle(field: FormField) {
    return html`
      <div class="multiple-lights field-with-help">
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
        ${this.contextHelp("About measuring multiple lights", html`<p>
          Measuring multiple identical lights together increases the load, making very low power use easier to measure accurately.
          </p><p>
          Select up to three individual lights. For larger sets, select a native Zigbee or Hue group, or create a
          <a href=${HOME_ASSISTANT_GROUP_GUIDE_URL} target="_blank" rel="noopener noreferrer">Home Assistant light group</a>,
          then enter the total number of physical lights.
          </p><p>
          <a
            class="help-link"
            href=${MULTIPLE_LIGHTS_GUIDE_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Learn more about measuring multiple identical lights"
          >Multiple-light measurement guide ↗</a>
        </p>`)}
      </div>
    `;
  }

  private contextHelp(label: string, content: unknown, className = "") {
    return html`<details class="context-help ${className}" @keydown=${this.helpKeydown} @focusout=${this.helpFocusOut}>
      <summary aria-label=${label} title=${label}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9"></circle>
          <path d="M9.75 9a2.4 2.4 0 0 1 4.57 1c0 1.75-2.32 2.1-2.32 3.5M12 17h.01"></path>
        </svg>
      </summary>
      <div class="help-content">${content}</div>
    </details>`;
  }

  private helpKeydown(event: KeyboardEvent): void {
    if (event.key !== "Escape") return;
    const help = event.currentTarget as HTMLDetailsElement;
    help.open = false;
    help.querySelector("summary")?.focus();
    event.stopPropagation();
  }

  private helpFocusOut(event: FocusEvent): void {
    const help = event.currentTarget as HTMLDetailsElement;
    if (!help.contains(event.relatedTarget as Node | null)) help.open = false;
  }

  private renderField(field: FormField) {
    const definition = this.definition;
    if (!definition || !this.fieldState || !visible(field, this.fieldState)) return nothing;
    const name = field.name;
    if (this.dummyController && field.role === "controller") return nothing;
    if (field.derived_from) return this.renderDerivedCount(field);
    const stored = this.request && requestFieldValue(this.request, field);
    if (field.control === "boolean") {
      return html`<label class="check"><input type="checkbox" name=${name} .checked=${Boolean(stored ?? field.default)} />${field.label}</label>`;
    }
    if (field.control === "entity") {
      const value = (stored ?? field.default ?? "").toString();
      const source = narrowingField(definition, field);
      const domains = source
        ? [entityDomain(definition, field, selectValue(source, this.fieldState))].filter((domain): domain is string => Boolean(domain))
        : this.fieldDomains(field);
      const failed = field.all_entities
        ? (this.deviceEntityErrors["*"] ? "*" : undefined)
        : domains.find((domain) => this.deviceEntityErrors[domain]);
      if (failed) {
        return html`<div class="notice error" role="alert">Could not load ${field.label.toLowerCase()} entities: ${this.deviceEntityErrors[failed]}</div>`;
      }
      const entities = entityChoices(field, this.fieldState, domains);
      if (field.multiple && (field.role !== "controller" || this.multipleLights)) {
        return this.renderMultiEntity(field, entities);
      }
      let selected = field.multiple ? selectedEntityId(field, this.fieldState) || value : value;
      if (!selected && field.same_device_only && entities.length === 1) selected = entities[0]?.entity_id ?? "";
      const relatedMissing = Boolean(field.same_device_only && field.related_to && entities.length === 0);
      const selector = entitySelect(name, field.label, entities, {
        selected,
        required: field.required,
        onChange: this.entityChanged,
      });
      if (!field.hint && !relatedMissing) return selector;
      return html`<div class="field-block">
        ${selector}
        ${fieldHint(field.hint ?? "")}
        ${relatedMissing ? html`<p class="notice error" role="alert">No usable battery percentage sensor was found on the same Home Assistant device. PowerCalc vacuum profiles require one; expose or add that sensor before recording.</p>` : nothing}
      </div>`;
    }
    if (field.control === "select") {
      const value = selectValue(field, this.fieldState) ?? (stored ?? field.default ?? "").toString();
      const affectsAnother = definition.fields.some(
        (candidate) => candidate.narrowed_by === name || Object.hasOwn(candidate.visible_when ?? {}, name),
      );
      const selectedOption = field.options.find((option) => option.value === value);
      return html`<div class="field-block">${optionSelect(name, field.label, field.options, {
        selected: value,
        required: field.required,
        onChange: affectsAnother ? this.selectChanged : null,
      })}${this.optionGuidance(selectedOption)}</div>`;
    }
    if (name === "export_filename" && definition.measure_type === "recorder") {
      return this.valueField(field, recorderExportFilename(recorderPurpose(this.fieldState), (stored ?? field.default ?? "").toString()));
    }
    return this.valueField(field, (stored ?? field.default ?? "").toString());
  }

  private optionGuidance(option?: FormFieldOption) {
    if (!option?.description && !option?.guidance?.length) return nothing;
    const guidanceItems = option.guidance?.map((item) => html`<li>${item}</li>`);
    return html`<div class="select-guidance">
      ${option.description ? html`<p class="muted">${option.description}</p>` : nothing}
      ${guidanceItems?.length ? html`<ul>${guidanceItems}</ul>` : nothing}
    </div>`;
  }

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

  private renderDerivedCount(field: FormField) {
    if (!this.multipleLights) return html`<input type="hidden" name=${field.name} value="1" />`;
    const source = this.definition?.fields.find((candidate) => candidate.name === field.derived_from);
    const derived = source && this.fieldState ? selectedEntityIds(source, this.fieldState).length : 0;
    const stored = this.request && requestFieldValue(this.request, field);
    const value = this.derivedCountOverride
      ?? (derived > 1 ? String(derived) : (stored ?? field.default ?? "").toString());
    return html`<div class="field-with-help">
      ${this.valueField({ ...field, hint: undefined }, value, this.derivedCountChanged)}
      ${this.contextHelp(field.label, html`<p>Total number of identical physical lights, including all members of a group. Measured power is divided by this value to calculate power per light.</p>`)}
    </div>`;
  }

  private renderMultiEntity(field: FormField, entities: EntityDescriptor[]) {
    if (this.definition?.measure_type === "light" && field.role === "controller") {
      return html`<measure-combobox
        name=${field.name}
        label=${field.plural_label || field.label}
        .value=${this.fieldState ? selectedEntityIds(field, this.fieldState) : []}
        .options=${entities.map((entity) => ({ value: entity.entity_id, label: `${entity.name} · ${entity.entity_id}` }))}
        placeholder="Select lights"
        ?required=${field.required}
        multiple
        @combobox-change=${(event: CustomEvent<{ value: string[] }>) => this.changeEntities(field.name, event.detail.value)}
      ></measure-combobox>`;
    }
    return renderEntityList({
      field,
      entities,
      rows: this.fieldState ? entityRows(field, this.fieldState) : [],
      onChange: (rows) => this.changeEntities(field.name, rows),
    });
  }

  private fieldDomains(field: FormField): string[] {
    return field.entity_domains ?? [];
  }

  private renderMultiSelect(field: FormField) {
    const selected = this.fieldState ? selectedOptions(field, this.fieldState) : [];
    return html`
      <fieldset>
        <legend>${this.definition?.measure_type === "light" && field.name === "modes" ? "What do you want to measure?" : field.label}</legend>
        <div class="checks">
          ${(this.fieldState ? availableOptions(field, this.fieldState) : []).map((option) => html`
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

  private readonly entityChanged = (event: Event): void => {
    const select = event.currentTarget as HTMLInputElement;
    this.changeEntities(select.name, [select.value]);
    for (const dependent of this.definition?.fields.filter((field) => field.related_to === select.name) ?? []) {
      this.changeEntities(dependent.name, []);
    }
  };

  private changeEntities(name: string, rows: string[]): void {
    emit<EntitySelectionChange>(this, "entity-selection-change", { name, rows });
  }

  private readonly selectChanged = (event: Event): void => {
    const select = event.currentTarget as HTMLInputElement;
    emit<SelectValueChange>(this, "select-value-change", { name: select.name, value: select.value });
    const form = select.closest("form");
    if (this.definition) {
      emit<string[]>(this, "entity-domains-requested", entityDomains(this.definition, form ? new FormData(form) : undefined));
    }
  };

  private multiSelectChanged(field: FormField): () => void {
    return () => {
      const boxes = [...this.querySelectorAll<HTMLInputElement>(`input[name="${field.name}"]`)];
      emit<MultiSelectionChange>(this, "multi-selection-change", {
        name: field.name,
        values: boxes.filter((box) => box.checked).map((box) => box.value),
      });
    };
  }

  private readonly multipleLightsChanged = (event: Event): void => {
    const input = event.currentTarget as HTMLInputElement;
    emit<MultipleLightsChange>(this, "multiple-lights-change", {
      checked: input.checked,
      fieldName: input.dataset.field ?? "",
    });
  };

  private readonly derivedCountChanged = (event: Event): void => {
    emit<string>(this, "derived-count-change", (event.currentTarget as HTMLInputElement).value);
  };

}
