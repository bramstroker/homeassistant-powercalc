import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property } from "lit/decorators.js";
import { sharedStyles } from "../../styles";
import { emit } from "../../utils/events";

@customElement("measure-string-list-input")
export class StringListInput extends LitElement {
  static readonly formAssociated = true;

  @property({ type: String }) name = "";
  @property({ type: String }) label = "";
  @property({ type: String }) itemLabel = "Entry";
  @property({ attribute: false }) value: string[] = [];
  @property({ type: String }) placeholder = "";
  @property({ type: String }) hint = "";
  @property({ type: String }) error = "";
  @property({ type: String }) inputMode: "text" | "numeric" = "text";
  @property({ type: Boolean }) disabled = false;

  private readonly internals = this.createInternals();

  static readonly styles = [sharedStyles, css`
    :host { display: grid; min-width: 0; }
    fieldset { gap: 0.4rem; }
    legend { margin-bottom: 0.4rem; }
    .rows { display: grid; gap: 0.5rem; }
    .row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 0.5rem; align-items: center; }
    .row-action { display: grid; place-items: center; width: 44px; padding: 0; }
    .row-action svg { width: 20px; height: 20px; }
  `];

  protected updated(changed: PropertyValues<this>): void {
    if (changed.has("value") || changed.has("name") || changed.has("disabled") || changed.has("error")) {
      this.syncFormControl();
    }
  }

  render() {
    const values = this.rows();
    const describedBy = [this.hint ? "list-hint" : "", this.error ? "list-error" : ""].filter(Boolean).join(" ");
    return html`
      <fieldset ?disabled=${this.disabled}>
        <legend>${this.label}</legend>
        <div class="rows">
          ${values.map((value, index) => html`
            <div class="row">
              <label>
                <span class="sr-only">${this.itemLabel} ${index + 1}</span>
                <input
                  name=${this.name}
                  type="text"
                  inputmode=${this.inputMode}
                  .value=${value}
                  placeholder=${this.placeholder}
                  autocomplete="off"
                  aria-invalid=${this.error ? "true" : "false"}
                  aria-describedby=${describedBy || nothing}
                  @input=${(event: InputEvent) => this.rowChanged(index, event)}
                />
              </label>
              ${values.length > 1 ? this.renderRemoveButton(index) : nothing}
              ${index === values.length - 1 ? this.renderAddButton(value) : nothing}
            </div>
          `)}
        </div>
        ${this.hint ? html`<small id="list-hint" class="field-hint">${this.hint}</small>` : nothing}
        ${this.error ? html`<small id="list-error" class="field-hint error">${this.error}</small>` : nothing}
      </fieldset>
    `;
  }

  private renderRemoveButton(index: number) {
    return html`<button
      class="row-action remove danger"
      type="button"
      aria-label=${`Remove ${this.itemLabel.toLowerCase()} ${index + 1}`}
      title=${`Remove ${this.itemLabel.toLowerCase()} ${index + 1}`}
      @click=${() => void this.removeRow(index)}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 10v6M14 10v6"></path>
      </svg>
    </button>`;
  }

  private renderAddButton(value: string) {
    const label = `Add another ${this.itemLabel.toLowerCase()}`;
    return html`<button
      class="row-action add"
      type="button"
      aria-label=${label}
      title=${label}
      ?disabled=${!value.trim()}
      @click=${this.addRow}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
        <path d="M12 5v14M5 12h14"></path>
      </svg>
    </button>`;
  }

  private rowChanged(index: number, event: InputEvent): void {
    event.stopPropagation();
    const values = [...this.rows()];
    values[index] = (event.currentTarget as HTMLInputElement).value;
    this.change(values);
  }

  private async addRow(): Promise<void> {
    this.change([...this.rows(), ""]);
    await this.updateComplete;
    this.inputs().at(-1)?.focus();
  }

  private async removeRow(index: number): Promise<void> {
    const values = this.rows().filter((_, position) => position !== index);
    this.change(values);
    await this.updateComplete;
    const inputs = this.inputs();
    inputs[Math.min(index, inputs.length - 1)]?.focus();
  }

  private change(values: string[]): void {
    this.value = values;
    this.syncFormControl();
    emit<{ value: string[] }>(this, "list-input-change", { value: values });
  }

  private rows(): string[] {
    return this.value.length ? this.value : [""];
  }

  private inputs(): HTMLInputElement[] {
    return [...this.renderRoot.querySelectorAll<HTMLInputElement>("input")];
  }

  private submittedValues(): string[] {
    return this.value.map((value) => value.trim()).filter(Boolean);
  }

  private syncFormControl(): void {
    const values = this.submittedValues();
    const formValue = new FormData();
    for (const value of values) formValue.append(this.name, value);
    this.internals?.setFormValue(this.disabled || !this.name || !values.length ? null : formValue);
    this.internals?.setValidity(
      this.error ? { customError: true } : {},
      this.error,
      this.inputs()[0],
    );
  }

  private createInternals(): ElementInternals | undefined {
    if (typeof this.attachInternals !== "function") return undefined;
    const internals = this.attachInternals();
    return typeof internals.setFormValue === "function" ? internals : undefined;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "measure-string-list-input": StringListInput;
  }
}
