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
});
