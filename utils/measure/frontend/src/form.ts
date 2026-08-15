/** Readers for submitted form values. A missing or non-text entry always reads as empty, never `null`. */

export function formText(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value.trim() : "";
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
