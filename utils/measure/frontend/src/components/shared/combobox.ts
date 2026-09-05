import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { sharedStyles } from "../../styles";

export interface ComboboxOption {
  value: string;
  label: string;
  disabled?: boolean;
}

@customElement("measure-combobox")
export class Combobox extends LitElement {
  static readonly formAssociated = true;

  @property({ type: String }) name = "";
  @property({ type: String }) label = "";
  @property({ attribute: false }) value: string | string[] = "";
  @property({ type: String }) placeholder = "";
  @property({ type: String }) hint = "";
  @property({ type: String }) error = "";
  @property({ attribute: false }) options: ComboboxOption[] = [];
  @property({ type: Boolean }) required = false;
  @property({ type: Boolean }) allowCustom = false;
  @property({ type: Boolean }) multiple = false;
  @property({ type: Boolean }) disabled = false;

  @state() private query = "";
  @state() private filter = "";
  @state() private open = false;
  @state() private active = -1;

  private readonly internals = this.createInternals();

  static readonly styles = [sharedStyles, css`
    :host { display: grid; gap: 0.4rem; min-width: 0; }
    .control { position: relative; min-width: 0; }
    input { padding-right: 2.75rem; }
    .control.multiple {
      display: flex; flex-wrap: wrap; align-items: center; gap: 0.45rem; min-height: 44px;
      padding: 0.35rem 2.75rem 0.35rem 0.45rem; border: 1px solid var(--line); border-radius: 9px;
      background: var(--field);
    }
    .control.multiple:focus-within { border-color: var(--signal); box-shadow: 0 0 0 2px color-mix(in srgb, var(--signal) 28%, transparent); }
    .control.multiple.invalid { border-color: var(--danger); box-shadow: inset 0 0 0 1px var(--danger); }
    .control.multiple input {
      flex: 1 1 150px; width: auto; min-width: 8rem; min-height: 32px; padding: 0.25rem 0;
      border: 0; border-radius: 0; background: transparent; box-shadow: none;
    }
    .control.multiple input:focus { border: 0; outline: 0; box-shadow: none; }
    input[readonly] { cursor: pointer; }
    .tag {
      display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.35rem 0.5rem;
      border-radius: 999px; background: color-mix(in srgb, var(--signal) 18%, var(--surface-raised));
      font-size: 0.78rem; white-space: nowrap;
    }
    .tag button { min-height: 0; padding: 0; border: 0; background: transparent; color: var(--muted); font: inherit; line-height: 1; }
    .tag button:hover:not(:disabled) { border: 0; background: transparent; color: var(--ink); transform: none; }
    .toggle {
      position: absolute; inset: 1px 1px 1px auto; width: 2.65rem; min-height: 0; padding: 0; border: 0;
      border-radius: 0 8px 8px 0; background: transparent; color: var(--muted); font-size: 0.8rem;
    }
    .toggle:hover:not(:disabled) { border: 0; background: color-mix(in srgb, var(--signal) 10%, transparent); transform: none; }
    .menu {
      position: absolute; z-index: 20; top: calc(100% + 0.35rem); right: 0; left: 0; max-height: 260px;
      overflow-y: auto; padding: 0.35rem; border: 1px solid var(--line); border-radius: 10px;
      background: var(--surface-raised); box-shadow: 0 14px 34px rgb(0 0 0 / 38%);
    }
    .option { padding: 0.62rem 0.7rem; border-radius: 7px; color: var(--ink); cursor: pointer; font-size: 0.82rem; line-height: 1.25; }
    .option:hover, .option.active { background: color-mix(in srgb, var(--signal) 18%, transparent); color: var(--signal-strong); }
    .option.disabled { opacity: 0.45; cursor: not-allowed; }
    .empty { margin: 0; padding: 0.7rem; color: var(--muted); font-size: 0.78rem; line-height: 1.4; }
  `];

  protected willUpdate(changed: PropertyValues<this>): void {
    if (!this.multiple && (changed.has("value") || changed.has("options"))) this.query = this.displayValue(this.singleValue());
  }

  protected updated(): void {
    this.syncFormControl();
  }

  render() {
    return html`
      ${this.renderLabel()}
      ${this.renderControl()}
      ${this.renderSupportingText()}
      <slot name="value" hidden></slot>
    `;
  }

  private renderLabel() {
    const requiredMarker = this.required
      ? html` <span class="required-marker" aria-hidden="true">*</span>`
      : nothing;
    return html`<label for="combobox-input"><span>${this.label}${requiredMarker}</span></label>`;
  }

  private renderControl() {
    const describedBy = [this.hint ? "combobox-hint" : "", this.error ? "combobox-error" : ""]
      .filter(Boolean)
      .join(" ");
    return html`
      <div class=${this.controlClass()} @focusout=${this.focusOut}>
        ${this.renderSelectedValues()}
        <input
          id="combobox-input"
          .value=${this.query}
          ?required=${this.required}
          ?disabled=${this.disabled}
          ?readonly=${!this.searchable}
          autocomplete="off"
          placeholder=${this.inputPlaceholder()}
          role="combobox"
          aria-autocomplete=${this.searchable ? "list" : "none"}
          aria-readonly=${this.searchable ? nothing : "true"}
          aria-invalid=${this.error ? "true" : "false"}
          aria-describedby=${describedBy || nothing}
          aria-controls="combobox-options"
          aria-multiselectable=${this.multiple ? "true" : nothing}
          aria-expanded=${this.open ? "true" : "false"}
          aria-activedescendant=${this.active >= 0 ? `combobox-option-${this.active}` : nothing}
          @focus=${this.openOptions}
          @click=${this.inputClicked}
          @input=${this.inputChanged}
          @keydown=${this.keydown}
        />
        <button class="toggle" type="button" aria-label=${`Show ${this.label.toLowerCase()} options`} ?disabled=${this.disabled} @click=${this.toggle}>
          ${this.open ? "▲" : "▼"}
        </button>
        ${this.open ? this.renderMenu(this.filteredOptions()) : nothing}
      </div>
    `;
  }

  private renderSupportingText() {
    return html`
      ${this.hint ? html`<small id="combobox-hint" class="field-hint">${this.hint}</small>` : nothing}
      ${this.error ? html`<small id="combobox-error" class="field-hint error">${this.error}</small>` : nothing}
    `;
  }

  private renderSelectedValues() {
    if (!this.multiple) return nothing;
    return this.values().map((value) => html`
      <span class="tag">
        ${this.displayValue(value)}
        <button type="button" ?disabled=${this.disabled} aria-label=${`Remove ${this.displayValue(value)}`} @click=${() => this.removeValue(value)}>×</button>
      </span>
    `);
  }

  private inputPlaceholder(): string {
    return this.multiple && this.values().length ? "Add another…" : this.placeholder;
  }

  private renderMenu(options: ComboboxOption[]) {
    const content = options.length
      ? options.map((option, index) => this.renderOption(option, index))
      : html`<p class="empty">${this.emptyMessage()}</p>`;
    return html`<div id="combobox-options" class="menu" role="listbox" aria-label=${`${this.label} options`} aria-multiselectable=${this.multiple ? "true" : nothing}>${content}</div>`;
  }

  private renderOption(option: ComboboxOption, index: number) {
    return html`<div
      id=${`combobox-option-${index}`}
      class=${this.optionClass(option, index)}
      role="option"
      aria-selected=${this.isSelected(option.value) ? "true" : "false"}
      aria-disabled=${option.disabled ? "true" : "false"}
      @mousedown=${(event: MouseEvent) => event.preventDefault()}
      @mousemove=${() => this.activateOption(option, index)}
      @click=${() => this.select(option)}
    >${option.label}</div>`;
  }

  private emptyMessage(): string {
    return this.allowCustom
      ? "No existing option matches. This value will be saved as a custom entry."
      : "No matching options.";
  }

  private filteredOptions(): ComboboxOption[] {
    if (!this.searchable) return this.options.filter((option) => !this.multiple || !this.values().includes(option.value));
    const terms = this.filter.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    const selected = new Set(this.multiple ? this.values() : []);
    return this.options.filter((option) => {
      if (selected.has(option.value)) return false;
      if (!terms.length) return true;
      const text = `${option.label} ${option.value}`.toLocaleLowerCase();
      return terms.every((term) => text.includes(term));
    });
  }

  private displayValue(value: string): string {
    return this.options.find((option) => option.value === value)?.label ?? value;
  }

  private hiddenInput(): HTMLInputElement | null {
    return this.querySelector('input[slot="value"]');
  }

  private createInternals(): ElementInternals | undefined {
    if (typeof this.attachInternals !== "function") return undefined;
    const internals = this.attachInternals();
    return typeof internals.setFormValue === "function" ? internals : undefined;
  }

  private syncFormControl(): void {
    if (this.multiple) {
      const formValue = new FormData();
      for (const value of this.values()) formValue.append(this.name, value);
      this.internals?.setFormValue(this.disabled || !this.name || !this.values().length ? null : formValue);
    } else {
      this.internals?.setFormValue(this.disabled || !this.name ? null : this.singleValue());
    }
    const input = this.renderRoot.querySelector<HTMLInputElement>("input");
    const missing = !this.disabled && this.required && (this.multiple ? !this.values().length : !this.singleValue());
    this.internals?.setValidity(
      missing ? { valueMissing: true } : {},
      missing ? `Select or enter ${this.label.toLowerCase()}.` : "",
      input ?? undefined,
    );
    const hidden = this.hiddenInput();
    if (hidden && !this.multiple) {
      hidden.value = this.singleValue();
      hidden.disabled = Boolean(this.internals) || this.disabled;
    } else if (hidden) {
      hidden.disabled = true;
    }
  }

  private openOptions() {
    this.filter = "";
    this.open = true;
    this.active = -1;
  }

  private toggle() {
    this.open = !this.open;
    if (this.open) this.renderRoot.querySelector<HTMLInputElement>("input")?.focus();
  }

  private inputClicked(): void {
    if (!this.open) this.openOptions();
  }

  private inputChanged(event: Event) {
    if (!this.searchable) return;
    this.query = (event.currentTarget as HTMLInputElement).value;
    this.filter = this.query;
    this.open = true;
    this.active = -1;
    if (this.allowCustom && !this.multiple) this.commit(this.query, false);
  }

  private keydown(event: KeyboardEvent) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      this.moveActiveOption(event);
      return;
    }
    if (event.key === "Enter") {
      this.selectOnEnter(event);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      this.closeAndRestore();
    }
  }

  private moveActiveOption(event: KeyboardEvent): void {
    event.preventDefault();
    this.open = true;
    const available = this.filteredOptions()
      .map((option, index) => ({ option, index }))
      .filter(({ option }) => !option.disabled);
    if (!available.length) return;
    const current = available.findIndex(({ index }) => index === this.active);
    const increment = event.key === "ArrowDown" ? 1 : -1;
    let next = (current + increment + available.length) % available.length;
    if (current < 0) next = event.key === "ArrowDown" ? 0 : available.length - 1;
    this.active = available[next]!.index;
    void this.updateComplete.then(() => this.renderRoot.querySelector(`#combobox-option-${this.active}`)?.scrollIntoView?.({ block: "nearest" }));
  }

  private selectOnEnter(event: KeyboardEvent): void {
    const options = this.filteredOptions();
    const option = this.enterOption(options);
    if (option && !option.disabled) {
      event.preventDefault();
      this.select(option);
    } else if (this.multiple && this.allowCustom && this.query.trim()) {
      event.preventDefault();
      this.add(this.query.trim());
    }
  }

  private enterOption(options: ComboboxOption[]): ComboboxOption | undefined {
    if (!this.open) return undefined;
    return this.active >= 0 ? options[this.active] : this.enterFallback(options);
  }

  /**
   * Option Enter commits when nothing was highlighted with the arrow keys. A typed query
   * picks the top match, except when the query is itself a valid custom value: choosing an
   * option there would silently discard what was typed. Without a query to go on (a readonly
   * list) Enter commits nothing, so an option is only ever chosen deliberately.
   */
  private enterFallback(options: ComboboxOption[]): ComboboxOption | undefined {
    if (this.allowCustom) {
      const query = this.query.trim().toLocaleLowerCase();
      return query
        ? options.find((option) => !option.disabled && option.label.toLocaleLowerCase() === query)
        : undefined;
    }
    return this.searchable ? options.find((option) => !option.disabled) : undefined;
  }

  private select(option: ComboboxOption) {
    if (option.disabled) return;
    if (this.multiple) {
      this.add(option.value);
      return;
    }
    this.query = option.label;
    this.filter = "";
    this.commit(option.value, true);
    this.open = false;
    this.active = -1;
    this.renderRoot.querySelector<HTMLInputElement>("input")?.focus();
  }

  private activateOption(option: ComboboxOption, index: number): void {
    if (!option.disabled) this.active = index;
  }

  private commit(value: string, emitChange: boolean) {
    this.value = value;
    const hidden = this.hiddenInput();
    if (hidden) {
      hidden.value = value;
      if (emitChange) hidden.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    }
    this.syncFormControl();
    this.dispatchEvent(new CustomEvent("combobox-change", { detail: { value }, bubbles: true, composed: true }));
  }

  private focusOut(): void {
    queueMicrotask(() => {
      const activeElement = this.shadowRoot?.activeElement;
      if (activeElement && this.containsFocusTarget(activeElement)) return;
      this.closeAndRestore();
    });
  }

  private containsFocusTarget(target: Node): boolean {
    return this.renderRoot.contains(target);
  }

  private closeAndRestore() {
    this.open = false;
    this.active = -1;
    if (this.multiple) this.query = "";
    else if (!this.allowCustom) this.query = this.displayValue(this.singleValue());
  }

  private add(value: string): void {
    if (!value || this.values().includes(value)) return;
    this.value = [...this.values(), value];
    this.query = "";
    this.filter = "";
    this.active = -1;
    this.open = true;
    this.changed();
  }

  private removeValue(value: string): void {
    this.value = this.values().filter((candidate) => candidate !== value);
    this.changed();
  }

  private changed(): void {
    this.syncFormControl();
    this.dispatchEvent(new CustomEvent("combobox-change", { detail: { value: this.value }, bubbles: true, composed: true }));
  }

  private values(): string[] {
    if (Array.isArray(this.value)) return this.value;
    return this.value ? [this.value] : [];
  }

  private singleValue(): string {
    if (Array.isArray(this.value)) return this.value[0] ?? "";
    return this.value;
  }

  private isSelected(value: string): boolean {
    return this.multiple ? this.values().includes(value) : this.singleValue() === value;
  }

  private controlClass(): string {
    return ["control", this.multiple ? "multiple" : "", this.error ? "invalid" : ""].filter(Boolean).join(" ");
  }

  private get searchable(): boolean {
    return this.allowCustom || this.options.length >= 10;
  }

  private optionClass(option: ComboboxOption, index: number): string {
    return ["option", index === this.active ? "active" : "", option.disabled ? "disabled" : ""].filter(Boolean).join(" ");
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "measure-combobox": Combobox;
  }
}
