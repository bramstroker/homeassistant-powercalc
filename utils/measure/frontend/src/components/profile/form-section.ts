import { LitElement, html, nothing } from "lit";
import { property } from "lit/decorators.js";
import type { ContributionDraft, ContributionFormValues, ContributionPreviewRequest } from "../../types";

export interface ProfileInputOptions {
  required?: boolean;
  placeholder?: string;
  hint?: string;
}

/** Shared light-DOM base so section inputs remain part of the parent native form. */
export abstract class ProfileFormSection extends LitElement {
  @property({ attribute: false }) draft!: ContributionDraft;
  @property({ attribute: false }) values: ContributionFormValues = {};
  @property({ attribute: false }) errors: Record<string, string> = {};
  @property({ type: Boolean }) busy = false;

  protected createRenderRoot(): HTMLElement | DocumentFragment {
    return this;
  }

  protected fieldValue(name: string, fallback: unknown): string {
    return formValue(this.values[name] ?? fallback);
  }

  protected fieldError(name: string): string {
    return this.errors[name] ?? "";
  }

  protected renderFieldError(name: string) {
    const error = this.fieldError(name);
    if (!error) return nothing;
    return html`<small id=${`${name}-error`} class="field-hint error">${error}</small>`;
  }

  protected renderInput(
    name: keyof ContributionPreviewRequest,
    label: string,
    fallback: string,
    options: ProfileInputOptions = {},
  ) {
    const { required = true, placeholder = "", hint = "" } = options;
    const error = this.fieldError(name);
    const labelId = `${name}-label`;
    const hintId = `${name}-hint`;
    const errorId = `${name}-error`;
    const describedBy = [hint ? hintId : "", error ? errorId : ""].filter(Boolean).join(" ");
    return html`
      <label>
        <span id=${labelId}>${label}${required ? html` <span class="required-marker" aria-hidden="true">*</span>` : nothing}</span>
        <input
          name=${name}
          type=${name === "contributor_email" ? "email" : "text"}
          .value=${this.fieldValue(name, fallback)}
          ?required=${required}
          placeholder=${placeholder}
          autocomplete="off"
          aria-invalid=${error ? "true" : "false"}
          aria-labelledby=${labelId}
          aria-describedby=${describedBy || nothing}
        />
        ${hint ? html`<small id=${hintId} class="field-hint">${hint}</small>` : nothing}
        ${this.renderFieldError(name)}
      </label>`;
  }

  protected renderTextarea(name: "measure_description" | "notes", label: string, fallback: unknown) {
    const error = this.fieldError(name);
    const labelId = `${name}-label`;
    const errorId = `${name}-error`;
    return html`<label class="notes-field">
      <span id=${labelId}>${label}</span>
      <textarea
        name=${name}
        .value=${this.fieldValue(name, fallback)}
        aria-labelledby=${labelId}
        aria-invalid=${error ? "true" : "false"}
        aria-describedby=${error ? errorId : nothing}
      ></textarea>
      ${this.renderFieldError(name)}
    </label>`;
  }
}

export function formValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}
