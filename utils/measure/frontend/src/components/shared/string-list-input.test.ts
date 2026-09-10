import { afterEach, describe, expect, it, vi } from "vitest";
import { submittedForm } from "../../utils/form";
import { StringListInput } from "./string-list-input";

function mount(values: string[] = []): { form: HTMLFormElement; field: StringListInput } {
  const form = document.createElement("form");
  const field = new StringListInput();
  field.name = "barcodes";
  field.label = "GTIN / barcodes";
  field.itemLabel = "Barcode";
  field.value = values;
  form.append(field);
  document.body.append(form);
  return { form, field };
}

describe("string list input", () => {
  afterEach(() => document.body.replaceChildren());

  it("adds, submits and removes individual values", async () => {
    const { form, field } = mount(["12345678"]);
    await field.updateComplete;
    const changed = vi.fn();
    field.addEventListener("list-input-change", changed);

    field.shadowRoot!.querySelector<HTMLButtonElement>(".add")!.click();
    await field.updateComplete;
    const inputs = [...field.shadowRoot!.querySelectorAll<HTMLInputElement>("input")];
    expect(inputs).toHaveLength(2);
    expect(field.shadowRoot!.activeElement).toBe(inputs[1]);
    inputs[1]!.value = " 1234567890123 ";
    inputs[1]!.dispatchEvent(new InputEvent("input", { bubbles: true }));
    await field.updateComplete;

    expect(field.value).toEqual(["12345678", " 1234567890123 "]);
    expect(submittedForm(form).getAll("barcodes")).toEqual(["12345678", " 1234567890123 "]);
    field.shadowRoot!.querySelector<HTMLButtonElement>('[aria-label="Remove barcode 1"]')!.click();
    await field.updateComplete;
    expect(field.value).toEqual([" 1234567890123 "]);
    expect(field.shadowRoot!.querySelectorAll("input")).toHaveLength(1);
    expect(changed).toHaveBeenCalledTimes(3);
  });

  it("renders one empty input and exposes guidance and errors", async () => {
    const { form, field } = mount();
    field.hint = "Add one barcode per field.";
    field.error = "Enter a valid barcode.";
    field.inputMode = "numeric";
    await field.updateComplete;

    const input = field.shadowRoot!.querySelector("input")!;
    expect(input.inputMode).toBe("numeric");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toBe("list-hint list-error");
    expect(field.shadowRoot!.querySelectorAll("input")).toHaveLength(1);
    expect(field.shadowRoot!.querySelector<HTMLButtonElement>(".add")!.disabled).toBe(true);
    expect(submittedForm(form).getAll("barcodes")).toEqual([]);
  });
});
