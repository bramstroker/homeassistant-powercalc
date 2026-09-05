/** Readers for submitted form values. A missing or non-text entry always reads as empty, never `null`. */

export function formText(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value.trim() : "";
}

/** Read a finite string choice without asserting that arbitrary form data belongs to its union. */
export function formChoice<const T extends readonly string[]>(
  form: FormData,
  name: string,
  choices: T,
  fallback: T[number],
): T[number] {
  const value = formText(form, name);
  if (!value) return fallback;
  for (const choice of choices) {
    if (choice === value) return choice;
  }
  throw new Error(`The selected ${name.replaceAll("_", " ")} is invalid.`);
}

/** The same, keeping surrounding whitespace — for secrets and free-form notes where it may be meaningful. */
export function formRaw(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value : "";
}

export function formNumber(form: FormData, name: string): number {
  return Number(formText(form, name));
}

/** A checkbox: present in the submission only while it is ticked. */
export function formChecked(form: FormData, name: string): boolean {
  return form.has(name);
}

export function formList(form: FormData, name: string): string[] {
  return form.getAll(name).map(String);
}

/** A text value, or null when the field was left empty — the shape the settings API expects. */
export function formTextOrNull(form: FormData, name: string): string | null {
  return formText(form, name) || null;
}

interface FormValueElement extends Element {
  name: string;
  value: string | string[];
  disabled: boolean;
}

/**
 * Build submitted values and normalize form-associated custom elements.
 *
 * Browsers contribute these through ElementInternals. The explicit copy also supports test DOMs
 * and older webviews without form-associated custom-element support.
 */
export function submittedForm(form: HTMLFormElement): FormData {
  const data = new FormData(form);
  for (const control of form.querySelectorAll<FormValueElement>("measure-combobox")) {
    if (!control.name) continue;
    data.delete(control.name);
    if (control.disabled) continue;
    const values = Array.isArray(control.value) ? control.value : [control.value];
    for (const value of values) {
      if (value) data.append(control.name, value);
    }
  }
  return data;
}
