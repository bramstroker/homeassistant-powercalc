import type { Combobox } from "./combobox";
import "./combobox";

function createCombobox(allowCustom = false): { form: HTMLFormElement; picker: Combobox } {
  const form = document.createElement("form");
  const picker = document.createElement("measure-combobox");
  picker.name = "device";
  picker.label = "Device";
  picker.placeholder = "Search devices";
  picker.required = true;
  picker.allowCustom = allowCustom;
  picker.options = [
    { value: "sensor.office", label: "Office plug · sensor.office" },
    { value: "sensor.kitchen", label: "Kitchen plug · sensor.kitchen" },
    ...Array.from({ length: 8 }, (_, index) => ({ value: `sensor.extra_${index}`, label: `Extra plug ${index}` })),
  ];
  const fallback = document.createElement("input");
  fallback.type = "hidden";
  fallback.name = "device";
  fallback.slot = "value";
  picker.append(fallback);
  form.append(picker);
  document.body.append(form);
  return { form, picker };
}

describe("combobox", () => {
  it("filters, supports keyboard selection, and contributes the selected value to its form", async () => {
    const { form, picker } = createCombobox();
    await picker.updateComplete;
    const input = picker.shadowRoot?.querySelector("input") as HTMLInputElement;

    input.focus();
    input.value = "kitchen";
    input.dispatchEvent(new InputEvent("input", { bubbles: true }));
    await picker.updateComplete;

    expect([...picker.shadowRoot?.querySelectorAll(".option") ?? []].map((option) => option.textContent?.trim())).toEqual([
      "Kitchen plug · sensor.kitchen",
    ]);
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    await picker.updateComplete;
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await picker.updateComplete;

    expect(picker.value).toBe("sensor.kitchen");
    expect(input.value).toBe("Kitchen plug · sensor.kitchen");
    expect(new FormData(form).get("device")).toBe("sensor.kitchen");
    expect(input.getAttribute("aria-expanded")).toBe("false");
  });

  it("accepts a custom value when enabled", async () => {
    const { form, picker } = createCombobox(true);
    await picker.updateComplete;
    const input = picker.shadowRoot?.querySelector("input") as HTMLInputElement;

    input.value = "My calibrated meter";
    input.dispatchEvent(new InputEvent("input", { bubbles: true }));
    await picker.updateComplete;

    expect(picker.value).toBe("My calibrated meter");
    expect(picker.shadowRoot?.textContent).toContain("saved as a custom entry");
    expect(new FormData(form).get("device")).toBe("My calibrated meter");
  });

  it("opens short option lists without presenting an editable search field", async () => {
    const { picker } = createCombobox();
    picker.options = picker.options.slice(0, 4);
    await picker.updateComplete;
    const input = picker.shadowRoot?.querySelector("input") as HTMLInputElement;

    expect(input.readOnly).toBe(true);
    expect(input.getAttribute("aria-autocomplete")).toBe("none");
    input.focus();
    await picker.updateComplete;
    expect(picker.shadowRoot?.querySelectorAll(".option")).toHaveLength(4);
  });

  it("selects the first matching multi-select option with Enter and renders removable tags", async () => {
    const { picker } = createCombobox();
    picker.multiple = true;
    picker.value = ["sensor.office"];
    await picker.updateComplete;
    const input = picker.shadowRoot?.querySelector("input") as HTMLInputElement;

    expect(picker.shadowRoot?.querySelector('[aria-label="Remove Office plug · sensor.office"]')).not.toBeNull();
    expect(input.placeholder).toBe("Add another…");
    input.focus();
    input.value = "kitchen";
    input.dispatchEvent(new InputEvent("input", { bubbles: true }));
    await picker.updateComplete;
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await picker.updateComplete;

    expect(picker.value).toEqual(["sensor.office", "sensor.kitchen"]);
    expect(input.value).toBe("");
    (picker.shadowRoot?.querySelector('[aria-label="Remove Office plug · sensor.office"]') as HTMLButtonElement).click();
    await picker.updateComplete;
    expect(picker.value).toEqual(["sensor.kitchen"]);
    (picker.shadowRoot?.querySelector('[aria-label="Remove Kitchen plug · sensor.kitchen"]') as HTMLButtonElement).click();
    await picker.updateComplete;
    expect(input.placeholder).toBe("Search devices");
  });

  it("keeps a typed custom value on Enter unless it exactly matches an option", async () => {
    const { form, picker } = createCombobox(true);
    await picker.updateComplete;
    const input = picker.shadowRoot?.querySelector("input") as HTMLInputElement;
    input.focus();
    input.value = "Office plug";
    input.dispatchEvent(new InputEvent("input", { bubbles: true }));
    await picker.updateComplete;
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await picker.updateComplete;

    expect(picker.value).toBe("Office plug");
    expect(new FormData(form).get("device")).toBe("Office plug");

    input.value = "Kitchen plug · sensor.kitchen";
    input.dispatchEvent(new InputEvent("input", { bubbles: true }));
    await picker.updateComplete;
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await picker.updateComplete;

    expect(picker.value).toBe("sensor.kitchen");
  });

  it("commits a readonly option only once it is highlighted", async () => {
    const { picker } = createCombobox();
    picker.options = picker.options.slice(0, 4);
    await picker.updateComplete;
    const input = picker.shadowRoot?.querySelector("input") as HTMLInputElement;
    input.focus();
    await picker.updateComplete;
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await picker.updateComplete;
    expect(picker.value).toBe("");

    input.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    await picker.updateComplete;
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await picker.updateComplete;
    expect(picker.value).toBe("sensor.office");
  });
});
