import type { MeasureDefinition } from "../../types";
import type { SetupViewElement } from "../testing/fixtures";

export interface TestCombobox extends HTMLElement {
  label: string;
  value: string | string[];
  options: Array<{ value: string; label: string }>;
  updateComplete: Promise<boolean>;
  shadowRoot: ShadowRoot;
}

export function entityCombobox(element: SetupViewElement, name: string): TestCombobox {
  return element.shadowRoot.querySelector(`measure-combobox[name="${name}"]`) as TestCombobox;
}

export function selectEntity(picker: TestCombobox, value: string): void {
  picker.value = value;
  const input = picker.querySelector('input[slot="value"]') as HTMLInputElement;
  input.value = value;
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

export const recorderDefinition: MeasureDefinition = {
  measure_type: "recorder",
  label: "Recorder",
  description: "Record power and entity states.",
  icon: "⏺",
  model_id_example: "",
  product_name_example: "",
  parameters: [],
  supports_profile: false,
  supports_resume: false,
  fields: [
    { name: "power_entity_id", role: "power_meter", label: "Power sensor", control: "entity", required: true, options: [] },
    {
      name: "recorder_purpose", role: "attribute", label: "What do you want to create?", control: "select", required: true,
      default: "playbook", review: true,
      options: [
        { value: "playbook", label: "A Playbook CSV", description: "Record the playbook format." },
        {
          value: "complex_profile",
          label: "Data for a complex power profile (experimental)",
          description: "This workflow is not feature complete and does not create a profile model.json yet.",
        },
      ],
    },
    {
      name: "profile_recipe", role: "attribute", label: "Device type", control: "select", required: true,
      default: "generic", visible_when: { recorder_purpose: ["complex_profile"] }, review: true,
      options: [
        { value: "generic", label: "Generic device", description: "Choose relevant entities." },
        { value: "vacuum_robot", label: "Robot vacuum", description: "Capture the vacuum and battery.", guidance: ["Measure the complete dock at the wall outlet."] },
      ],
    },
    {
      name: "tracked_entity_ids", role: "attribute", label: "Tracked entity", plural_label: "Tracked entities",
      control: "entity", required: true, multiple: true, all_entities: true,
      visible_when: { recorder_purpose: ["complex_profile"], profile_recipe: ["generic"] }, options: [], review: true,
    },
    {
      name: "vacuum_entity_id", role: "attribute", label: "Vacuum", control: "entity", required: true,
      all_entities: true, entity_domains: ["vacuum"],
      visible_when: { recorder_purpose: ["complex_profile"], profile_recipe: ["vacuum_robot"] }, options: [], review: true,
    },
    {
      name: "battery_entity_id", role: "attribute", label: "Battery level sensor", control: "entity", required: true,
      all_entities: true, entity_device_classes: ["battery"], related_to: "vacuum_entity_id", same_device_only: true,
      visible_when: { recorder_purpose: ["complex_profile"], profile_recipe: ["vacuum_robot"] }, options: [],
      hint: "PowerCalc vacuum profiles require a battery sensor.", review: true,
    },
    {
      name: "additional_entity_ids", role: "attribute", label: "Additional entity", plural_label: "Additional entities (optional)",
      control: "entity", required: false, multiple: true, all_entities: true, related_to: "vacuum_entity_id",
      visible_when: { recorder_purpose: ["complex_profile"], profile_recipe: ["vacuum_robot"] }, options: [], review: true,
    },
    { name: "export_filename", role: "attribute", label: "Export filename", control: "text", required: true, default: "record.csv", options: [] },
  ],
};
