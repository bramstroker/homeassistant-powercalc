export interface TestCombobox extends HTMLElement {
  value: string | string[];
  options: Array<{ value: string; label: string; disabled?: boolean }>;
}

export function settingsCombobox(root: ShadowRoot, name: string): TestCombobox {
  return root.querySelector(`measure-combobox[name="${name}"]`) as TestCombobox;
}

export function chooseOption(picker: TestCombobox, value: string): void {
  picker.value = value;
  const input = picker.querySelector('input[slot="value"]') as HTMLInputElement;
  input.value = value;
  input.dispatchEvent(new Event("change", { bubbles: true }));
}
