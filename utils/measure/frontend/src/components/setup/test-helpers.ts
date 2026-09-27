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
          description: "This experimental workflow creates fixed states_power models or composites from a secondary signal.",
        },
      ],
    },
    {
      name: "profile_recipe", role: "attribute", label: "Recording recipe", control: "select", required: true,
      default: "generic", visible_when: { recorder_purpose: ["complex_profile"] }, review: true,
      options: [
        { value: "generic", label: "Generic device", description: "Choose relevant entities." },
        { value: "vacuum_robot", label: "Robot vacuum", description: "Capture the vacuum and battery.", guidance: ["Measure the complete dock at the wall outlet."] },
      ],
    },
    {
      name: "profile_device_type", role: "attribute", label: "Profile device type", control: "select", required: true,
      default: "generic_iot", options: [
        { value: "generic_iot", label: "Generic IoT", entity_domains: ["media_player", "sensor"] },
        { value: "heating", label: "Heating", entity_domains: ["climate"] },
        { value: "camera", label: "Camera", entity_domains: ["camera"] },
        { value: "smart_switch", label: "Smart switch", entity_domains: ["light", "switch"] },
      ],
      visible_when: { recorder_purpose: ["complex_profile"], profile_recipe: ["generic"] }, review: true,
    },
    {
      name: "primary_entity_id", role: "attribute", label: "Primary entity", control: "entity", required: true,
      all_entities: true, narrowed_by: "profile_device_type", options: [],
      visible_when: { recorder_purpose: ["complex_profile"], profile_recipe: ["generic"] }, review: true,
    },
    {
      name: "tracked_entity_ids", role: "attribute", label: "Additional power signal", plural_label: "Additional power signals (optional)",
      control: "entity", required: false, multiple: true, all_entities: true, related_to: "primary_entity_id",
      visible_when: { recorder_purpose: ["complex_profile"], profile_recipe: ["generic"] }, options: [], review: true,
      hint: "Select other entities whose states may explain power changes.",
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
      hint: "Known activity entities are selected automatically, including linked dock washing, drying and auto-empty states. You can change the selection or add other relevant entities.",
    },
  ],
};
