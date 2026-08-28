import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { sharedStyles } from "../styles";

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
  @property({ type: String }) value = "";
  @property({ type: String }) placeholder = "";
  @property({ type: String }) hint = "";
  @property({ attribute: false }) options: ComboboxOption[] = [];
  @property({ type: Boolean }) required = false;
  @property({ type: Boolean }) allowCustom = false;
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

  protected willUpdate(changed: PropertyValues<this>) {
    if (changed.has("value") || changed.has("options")) this.query = this.displayValue(this.value);
  }

  protected updated(): void {
    this.syncFormControl();
  }

  render() {
    const options = this.filteredOptions();
    return html`
      <label for="combobox-input"><span>${this.label}</span></label>
      <div class="control" @focusout=${this.focusOut}>
        <input
          id="combobox-input"
          .value=${this.query}
          ?required=${this.required}
          ?disabled=${this.disabled}
          autocomplete="off"
          placeholder=${this.placeholder}
          role="combobox"
          aria-autocomplete="list"
          aria-controls="combobox-options"
          aria-expanded=${this.open ? "true" : "false"}
          aria-activedescendant=${this.active >= 0 ? `combobox-option-${this.active}` : nothing}
          @focus=${this.openOptions}
          @input=${this.inputChanged}
          @keydown=${this.keydown}
        />
        <button class="toggle" type="button" aria-label=${`Show ${this.label.toLowerCase()} options`} ?disabled=${this.disabled} @click=${this.toggle}>
          ${this.open ? "▲" : "▼"}
        </button>
        ${this.open ? html`
          <div id="combobox-options" class="menu" role="listbox" aria-label=${`${this.label} options`}>
            ${options.length
              ? options.map((option, index) => html`
                  <div
                    id=${`combobox-option-${index}`}
                    class=${this.optionClass(option, index)}
                    role="option"
                    aria-selected=${index === this.active ? "true" : "false"}
                    aria-disabled=${option.disabled ? "true" : "false"}
                    @mousedown=${(event: MouseEvent) => event.preventDefault()}
                    @mousemove=${() => this.activateOption(option, index)}
                    @click=${() => this.select(option)}
                  >${option.label}</div>
                `)
              : html`<p class="empty">${this.allowCustom
                ? "No existing option matches. This value will be saved as a custom entry."
                : "No matching options."}</p>`}
          </div>
        ` : nothing}
      </div>
      ${this.hint ? html`<small class="field-hint">${this.hint}</small>` : nothing}
      <slot name="value" hidden></slot>
    `;
  }

  private filteredOptions(): ComboboxOption[] {
    const terms = this.filter.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return this.options;
    return this.options.filter((option) => {
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
    this.internals?.setFormValue(this.disabled || !this.name ? null : this.value);
    const input = this.renderRoot.querySelector<HTMLInputElement>("input");
    const missing = !this.disabled && this.required && !this.value;
    this.internals?.setValidity(
      missing ? { valueMissing: true } : {},
      missing ? `Select or enter ${this.label.toLowerCase()}.` : "",
      input ?? undefined,
    );
    const hidden = this.hiddenInput();
    if (hidden) {
      hidden.value = this.value;
      hidden.disabled = Boolean(this.internals) || this.disabled;
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

  private inputChanged(event: Event) {
    this.query = (event.currentTarget as HTMLInputElement).value;
    this.filter = this.query;
    this.open = true;
    this.active = -1;
    if (this.allowCustom) this.commit(this.query, false);
  }

  private keydown(event: KeyboardEvent) {
    const options = this.filteredOptions();
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      this.open = true;
      const available = options.map((option, index) => ({ option, index })).filter(({ option }) => !option.disabled);
      if (!available.length) return;
      const current = available.findIndex(({ index }) => index === this.active);
      const increment = event.key === "ArrowDown" ? 1 : -1;
      const next = current < 0
        ? (event.key === "ArrowDown" ? 0 : available.length - 1)
        : (current + increment + available.length) % available.length;
      this.active = available[next]!.index;
      void this.updateComplete.then(() => this.renderRoot.querySelector(`#combobox-option-${this.active}`)?.scrollIntoView?.({ block: "nearest" }));
      return;
    }
    if (event.key === "Enter" && this.open && this.active >= 0) {
      event.preventDefault();
      const option = options[this.active];
      if (option) this.select(option);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      this.closeAndRestore();
    }
  }

  private select(option: ComboboxOption) {
    if (option.disabled) return;
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

  private focusOut(event: FocusEvent) {
    if (event.relatedTarget instanceof Node && this.containsFocusTarget(event.relatedTarget)) return;
    this.closeAndRestore();
  }

  private containsFocusTarget(target: Node): boolean {
    return this.renderRoot.contains(target);
  }

  private closeAndRestore() {
    this.open = false;
    this.active = -1;
    if (!this.allowCustom) this.query = this.displayValue(this.value);
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
