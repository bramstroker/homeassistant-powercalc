import {
  DEFAULT_SHELLY_USERNAME,
  POWER_METERS,
  POWER_METER_LIST,
  describe as describeMeter,
  hasVoltageReading,
  isAddressed,
  settingsFromForm,
  specFromRequest,
  specFromSettings,
  summarize,
} from "./registry";
import type { MeterContext } from "./registry";
import type { AppSettings, MeasurementRequest, PowerMeterSpec, PowerMeterType } from "../types";

const settings: AppSettings = {
  default_power_entity_id: "sensor.plug_power",
  default_measure_device: "Shelly Plug S",
  power_meter: "hass",
  shelly_ip: "192.0.2.20",
  shelly_username: "operator",
  kasa_ip: "192.0.2.30",
  fast_test_mode: false,
  measurement_defaults: { sleep_time: 1, sample_count: 1, sleep_time_sample: 1, max_retries: 5, max_nudges: 0 },
};

const context: MeterContext = {
  powers: [{ entity_id: "sensor.plug_power", name: "Plug power", related_voltage_entity_id: "sensor.plug_voltage" }],
  voltages: [{ entity_id: "sensor.plug_voltage", name: "Plug voltage" }],
};

const request = (power_meter: PowerMeterSpec): MeasurementRequest => ({
  measure_type: "average",
  model_id: "measurement",
  product_name: "Measurement",
  measure_device: "Shelly Plug S",
  generate_model: false,
  duration: 60,
  parameters: settings.measurement_defaults as MeasurementRequest["parameters"],
  resume_policy: "new",
  power_meter,
});

const form = (entries: Record<string, string | undefined>): FormData => {
  const data = new FormData();
  for (const [name, value] of Object.entries(entries)) if (value !== undefined) data.append(name, value);
  return data;
};

const TYPES: PowerMeterType[] = ["hass", "shelly", "kasa", "dummy"];

describe("power meter registry", () => {
  it("describes every type of meter exactly once, in picker order", () => {
    expect(POWER_METER_LIST.map((meter) => meter.type)).toEqual(TYPES);
    for (const type of TYPES) expect(POWER_METERS[type].type).toBe(type);
  });

  it("gives every meter a distinct label for the settings picker", () => {
    const labels = POWER_METER_LIST.map((meter) => meter.label);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it.each([
    { type: "hass" as const, expected: { type: "hass", entity_id: "sensor.plug_power", voltage_entity_id: "sensor.plug_voltage" } },
    { type: "shelly" as const, expected: { type: "shelly", device_ip: "192.0.2.20", username: "operator" } },
    { type: "kasa" as const, expected: { type: "kasa", device_ip: "192.0.2.30" } },
    { type: "dummy" as const, expected: { type: "dummy" } },
  ])("builds the $type meter the saved settings configure", ({ type, expected }) => {
    expect(specFromSettings({ ...settings, power_meter: type }, context)).toEqual(expected);
  });

  it("defaults an unconfigured app to an unaddressed Home Assistant sensor", () => {
    const spec = specFromSettings(undefined, context);
    expect(spec).toEqual({ type: "hass", entity_id: "", voltage_entity_id: null });
    expect(isAddressed(spec)).toBe(false);
  });

  it("falls back to the default Shelly username when none is saved", () => {
    const spec = specFromSettings({ ...settings, power_meter: "shelly", shelly_username: undefined }, context);
    expect(spec).toEqual({ type: "shelly", device_ip: "192.0.2.20", username: DEFAULT_SHELLY_USERNAME });
  });

  it("keeps the meter a session was started with, rather than the current default", () => {
    const stored: PowerMeterSpec = { type: "kasa", device_ip: "192.0.2.99" };
    expect(specFromRequest(request(stored), settings, context)).toEqual(stored);
  });

  it("falls back to the saved default when a draft names no meter yet", () => {
    expect(specFromRequest(undefined, settings, context)).toEqual(specFromSettings(settings, context));
  });

  it.each([
    { type: "hass", fields: { default_power_entity_id: "sensor.other" }, expected: { default_power_entity_id: "sensor.other", shelly_ip: null, kasa_ip: null } },
    { type: "shelly", fields: { shelly_ip: " 192.0.2.21 " }, expected: { default_power_entity_id: null, shelly_ip: "192.0.2.21", kasa_ip: null } },
    { type: "kasa", fields: { kasa_ip: "192.0.2.31" }, expected: { default_power_entity_id: null, shelly_ip: null, kasa_ip: "192.0.2.31" } },
    { type: "dummy", fields: {}, expected: { default_power_entity_id: null, shelly_ip: null, kasa_ip: null } },
  ])("saves only the address keys the selected $type meter owns", ({ type, fields, expected }) => {
    expect(settingsFromForm(form({ power_meter: type, ...fields }))).toEqual({ power_meter: type, ...expected });
  });

  it("ignores addresses left over from a meter that is no longer selected", () => {
    const saved = settingsFromForm(form({ power_meter: "kasa", kasa_ip: "192.0.2.31", shelly_ip: "192.0.2.21" }));
    expect(saved.shelly_ip).toBeNull();
  });

  it.each([
    { type: "hass" as const, addressed: { type: "hass", entity_id: "sensor.plug_power" }, blank: { type: "hass", entity_id: "" } },
    { type: "shelly" as const, addressed: { type: "shelly", device_ip: "192.0.2.20" }, blank: { type: "shelly", device_ip: "" } },
    { type: "kasa" as const, addressed: { type: "kasa", device_ip: "192.0.2.30" }, blank: { type: "kasa", device_ip: "" } },
  ] satisfies { type: PowerMeterType; addressed: PowerMeterSpec; blank: PowerMeterSpec }[])(
    "treats $type as unaddressed until its own address is filled in",
    ({ addressed, blank }) => {
      expect(isAddressed(addressed)).toBe(true);
      expect(isAddressed(blank)).toBe(false);
    },
  );

  it("needs no address for the synthetic meter", () => {
    expect(isAddressed({ type: "dummy" })).toBe(true);
  });

  it("has a voltage reading for directly polled meters, and only a paired sensor for Home Assistant", () => {
    expect(hasVoltageReading({ type: "shelly", device_ip: "192.0.2.20" })).toBe(true);
    expect(hasVoltageReading({ type: "kasa", device_ip: "192.0.2.30" })).toBe(true);
    expect(hasVoltageReading({ type: "hass", entity_id: "sensor.plug_power", voltage_entity_id: "sensor.v" })).toBe(true);
    expect(hasVoltageReading({ type: "hass", entity_id: "sensor.plug_power" })).toBe(false);
  });

  it("describes a Home Assistant sensor with its paired voltage sensor", () => {
    expect(describeMeter(specFromSettings(settings, context), context)).toEqual({
      source: "Plug power · sensor.plug_power",
      detail: "Voltage: Plug voltage · sensor.plug_voltage",
    });
  });

  it("says so when a Home Assistant sensor has no paired voltage sensor", () => {
    expect(describeMeter({ type: "hass", entity_id: "sensor.plug_power" }, context).detail)
      .toBe("Home Assistant power sensor");
  });

  it.each(TYPES)("always has something to say about a %s meter", (type) => {
    const spec = specFromSettings({ ...settings, power_meter: type }, context);
    const description = describeMeter(spec, context);
    expect(description.source).toBeTruthy();
    expect(description.detail).toBeTruthy();
    expect(summarize(spec)).toBeTruthy();
  });

  it("names a directly polled meter by label on the review screen, and a sensor by entity", () => {
    expect(summarize({ type: "hass", entity_id: "sensor.plug_power" })).toBe("sensor.plug_power");
    expect(summarize({ type: "shelly", device_ip: "192.0.2.20" })).toBe("Shelly plug");
  });

  it("only offers a dummy load on meters that read real power", () => {
    expect(POWER_METERS.dummy.supportsDummyLoad).toBe(false);
    for (const type of TYPES.filter((candidate) => candidate !== "dummy")) {
      expect(POWER_METERS[type].supportsDummyLoad).toBe(true);
    }
  });

  it("only validates meters that have real readings to check", () => {
    expect(POWER_METERS.dummy.validatable).toBe(false);
    expect(POWER_METERS.hass.validatable).toBe(true);
  });
});
