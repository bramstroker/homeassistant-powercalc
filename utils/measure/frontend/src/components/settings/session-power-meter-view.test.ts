import { SessionPowerMeterView } from "./session-power-meter-view";
import type { AppSettingsUpdate, SessionPowerMeter } from "../../types";
import { settings } from "../../testing/controller";
import { chooseOption, settingsCombobox, type TestCombobox } from "./test-helpers";

afterEach(() => document.body.replaceChildren());

async function editor(configuration: SessionPowerMeter): Promise<SessionPowerMeterView> {
  const element = new SessionPowerMeterView();
  element.settings = { ...settings, default_measure_device: "Global meter", default_power_entity_id: "sensor.global" };
  element.configuration = configuration;
  element.powers = [
    { entity_id: "sensor.local", name: "Local power", related_voltage_entity_id: "sensor.local_voltage" },
    { entity_id: "sensor.other", name: "Other power", related_voltage_entity_id: "sensor.other_voltage" },
  ];
  element.voltages = [
    { entity_id: "sensor.local_voltage", name: "Local voltage" },
    { entity_id: "sensor.other_voltage", name: "Other voltage" },
  ];
  document.body.append(element);
  await element.updateComplete;
  return element;
}

function selectOption(picker: TestCombobox, value: string): void {
  chooseOption(picker, value);
  picker.dispatchEvent(new CustomEvent("combobox-change", { detail: { value } }));
}

function submit(element: SessionPowerMeterView): SessionPowerMeter {
  const saved = vi.fn();
  element.addEventListener("save", saved);
  element.shadowRoot!.querySelector("form")!.dispatchEvent(new SubmitEvent("submit", { cancelable: true }));
  return (saved.mock.calls[0]![0] as CustomEvent<SessionPowerMeter>).detail;
}

describe("session power meter editor", () => {
  it.each<SessionPowerMeter>([
    { power_meter: { type: "hass", entity_id: "sensor.local", voltage_entity_id: "sensor.other_voltage" }, measure_device: "Local HA meter" },
    { power_meter: { type: "shelly", device_ip: "192.0.2.10", username: "local-user", channel: 2 }, measure_device: "Local Shelly" },
    { power_meter: { type: "kasa", device_ip: "192.0.2.20" }, measure_device: "Local Kasa" },
    { power_meter: { type: "dummy" }, measure_device: "Local dummy" },
  ])("starts from the session's $measure_device configuration and saves it locally", async (configuration) => {
    const element = await editor(configuration);
    expect(settingsCombobox(element.shadowRoot!, "default_measure_device").value).toBe(configuration.measure_device);
    expect(submit(element)).toEqual(configuration);
    expect(element.settings?.default_measure_device).toBe("Global meter");
    expect(element.shadowRoot!.textContent).toContain("Changes apply only to this draft");
    expect(element.shadowRoot!.querySelector('[name="default_measure_device_firmware"]')).toBeNull();
    expect(element.shadowRoot!.querySelector('[name="shelly_password"]')).toBeNull();
    expect(element.shadowRoot!.querySelector('[name="tapo_password"]')).toBeNull();
  });

  it("saves a name-only change without replacing the selected meter or its voltage sensor", async () => {
    const configuration: SessionPowerMeter = {
      power_meter: { type: "hass", entity_id: "sensor.local", voltage_entity_id: "sensor.other_voltage" },
      measure_device: "Local meter",
    };
    const element = await editor(configuration);
    selectOption(settingsCombobox(element.shadowRoot!, "default_measure_device"), "Renamed meter");
    await element.updateComplete;
    expect(submit(element)).toEqual({ ...configuration, measure_device: "Renamed meter" });
    expect(configuration.measure_device).toBe("Local meter");
  });

  it("associates the selected power sensor's voltage sensor and allows changing or clearing it", async () => {
    const element = await editor({ power_meter: { type: "hass", entity_id: "sensor.local" }, measure_device: "Local" });
    selectOption(settingsCombobox(element.shadowRoot!, "default_power_entity_id"), "sensor.other");
    await element.updateComplete;
    expect(submit(element).power_meter).toEqual({ type: "hass", entity_id: "sensor.other", voltage_entity_id: "sensor.other_voltage" });
    selectOption(settingsCombobox(element.shadowRoot!, "voltage_entity_id"), "sensor.local_voltage");
    await element.updateComplete;
    expect(submit(element).power_meter).toMatchObject({ voltage_entity_id: "sensor.local_voltage" });
    selectOption(settingsCombobox(element.shadowRoot!, "voltage_entity_id"), "");
    await element.updateComplete;
    expect(submit(element).power_meter).toMatchObject({ voltage_entity_id: null });
  });

  it("changes meter type, address and outlet without editing global settings", async () => {
    const element = await editor({ power_meter: { type: "hass", entity_id: "sensor.local" }, measure_device: "Local" });
    selectOption(settingsCombobox(element.shadowRoot!, "power_meter"), "shelly");
    await element.updateComplete;
    const address = element.shadowRoot!.querySelector<HTMLInputElement>('[name="shelly_ip"]')!;
    address.value = "192.0.2.50";
    address.dispatchEvent(new Event("input"));
    await element.updateComplete;
    const outlet = element.shadowRoot!.querySelector<HTMLInputElement>('[name="shelly_outlet"]')!;
    outlet.value = "4";
    outlet.dispatchEvent(new Event("input"));
    await element.updateComplete;
    expect(submit(element).power_meter).toEqual({ type: "shelly", device_ip: "192.0.2.50", username: "admin", channel: 3 });
    expect(element.settings?.power_meter).toBe("hass");
  });

  it("validates the edited meter without saving it", async () => {
    const element = await editor({ power_meter: { type: "kasa", device_ip: "192.0.2.20" }, measure_device: "Local" });
    const saved = vi.fn();
    const tested = vi.fn();
    element.addEventListener("save", saved);
    element.addEventListener("test", tested);
    const button = [...element.shadowRoot!.querySelectorAll("button")].find((button) => button.textContent?.includes("Validate measurement"))!;
    button.click();
    expect((tested.mock.calls[0]![0] as CustomEvent<AppSettingsUpdate>).detail).toMatchObject({
      power_meter: "kasa", kasa_ip: "192.0.2.20", default_measure_device: "Local",
    });
    expect(saved).not.toHaveBeenCalled();
  });

  it("discards edited fields when cancelled", async () => {
    const configuration: SessionPowerMeter = { power_meter: { type: "dummy" }, measure_device: "Local" };
    const element = await editor(configuration);
    const saved = vi.fn();
    const back = vi.fn();
    element.addEventListener("save", saved);
    element.addEventListener("back", back);
    selectOption(settingsCombobox(element.shadowRoot!, "default_measure_device"), "Unsaved edit");
    element.shadowRoot!.querySelector<HTMLButtonElement>('.actions button[type="button"]')!.click();
    expect(back).toHaveBeenCalledOnce();
    expect(saved).not.toHaveBeenCalled();
    expect(configuration.measure_device).toBe("Local");
    expect(element.settings?.default_measure_device).toBe("Global meter");
  });
});
