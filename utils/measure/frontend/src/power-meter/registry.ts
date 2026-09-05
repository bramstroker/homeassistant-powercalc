import type { AppSettings, EntityDescriptor, MeasurementRequest, PowerMeterSpec, PowerMeterType } from "../types";
import { formChoice, formTextOrNull } from "../utils/form";

/** Username Shelly devices are reached with unless the user configured another one. */
export const DEFAULT_SHELLY_USERNAME = "admin";

/** Entities the app knows about, which a meter may need in order to address or describe itself. */
export interface MeterContext {
  powers: EntityDescriptor[];
  voltages: EntityDescriptor[];
}

/** How a meter is presented: a headline source and a supporting detail line. */
export interface MeterDescription {
  source: string;
  detail: string;
}

/** The settings keys that name where readings come from. Each meter owns exactly the ones it uses. */
export interface PowerMeterSettings {
  default_power_entity_id: string | null;
  shelly_ip: string | null;
  kasa_ip: string | null;
}

/** The spec variant belonging to one type of meter. */
type SpecOf<T extends PowerMeterType> = Extract<PowerMeterSpec, { type: T }>;

/**
 * Everything the app needs to know about one type of power meter.
 *
 * Adding a meter means adding its variant to {@link PowerMeterSpec} and one entry here; the type
 * of {@link POWER_METERS} then makes the compiler name everything left out. The settings form's
 * own inputs are the one part that lives elsewhere, in `settings-view`, because they need that
 * view's handlers and credential state.
 */
export interface PowerMeterDescriptor<T extends PowerMeterType = PowerMeterType> {
  type: T;
  /** Name shown in the settings picker, and used wherever a meter is named without its address. */
  label: string;
  /** Whether readings can be validated up front. A synthetic meter has nothing to check. */
  validatable: boolean;
  /** Whether choosing this meter should look for devices on the network. */
  discoverable: boolean;
  /** Whether a resistive dummy load can be measured against this meter at all. */
  supportsDummyLoad: boolean;
  /** What the user should know about reading quality with this meter, when there is anything. */
  qualityNote?: string;
  /** The meter the saved app settings configure. */
  fromSettings(settings: AppSettings | undefined, context: MeterContext): SpecOf<T>;
  /** The settings keys this meter owns, read out of the settings form. Anything omitted saves as null. */
  settingsFromForm(form: FormData): Partial<PowerMeterSettings>;
  /** Whether the address this meter needs is filled in. */
  isAddressed(spec: SpecOf<T>): boolean;
  /** Whether a voltage reading is available, which dummy-load correction depends on. */
  hasVoltageReading(spec: SpecOf<T>): boolean;
  describe(spec: SpecOf<T>, context: MeterContext): MeterDescription;
}

/** Shared by every meter Powercalc reads over the network rather than through Home Assistant. */
const POLLED_DIRECTLY = "Powercalc polls this device directly, so Home Assistant sensor resolution and update-frequency checks do not apply.";

/** Every type of meter, in the order the settings picker offers them. */
export const POWER_METERS: { [T in PowerMeterType]: PowerMeterDescriptor<T> } = {
  hass: {
    type: "hass",
    label: "Home Assistant sensor",
    validatable: true,
    discoverable: false,
    supportsDummyLoad: true,
    qualityNote: "For reliable profiles, use a sensor with at least 0.1 W reported resolution and updates every 5 seconds or faster. Updates within 2 seconds are recommended.",
    fromSettings: (settings, context) => {
      const entityId = settings?.default_power_entity_id ?? "";
      return {
        type: "hass",
        entity_id: entityId,
        // The paired voltage sensor is what makes dummy-load correction possible.
        voltage_entity_id: relatedVoltageEntityId(context.powers, entityId) || null,
      };
    },
    settingsFromForm: (form) => ({ default_power_entity_id: formTextOrNull(form, "default_power_entity_id") }),
    isAddressed: (spec) => Boolean(spec.entity_id),
    hasVoltageReading: (spec) => Boolean(spec.voltage_entity_id),
    describe: (spec, context) => {
      const entity = context.powers.find((candidate) => candidate.entity_id === spec.entity_id);
      const voltage = context.voltages.find((candidate) => candidate.entity_id === spec.voltage_entity_id);
      const voltageName = voltage ? `${voltage.name} · ` : "";
      const voltageDetail = `Voltage: ${voltageName}${spec.voltage_entity_id}`;
      return {
        source: entity ? `${entity.name} · ${entity.entity_id}` : spec.entity_id,
        detail: spec.voltage_entity_id ? voltageDetail : "Home Assistant power sensor",
      };
    },
  },

  shelly: {
    type: "shelly",
    label: "Shelly plug",
    validatable: true,
    discoverable: true,
    supportsDummyLoad: true,
    qualityNote: POLLED_DIRECTLY,
    fromSettings: (settings) => ({
      type: "shelly",
      device_ip: settings?.shelly_ip ?? "",
      username: settings?.shelly_username ?? DEFAULT_SHELLY_USERNAME,
    }),
    settingsFromForm: (form) => ({ shelly_ip: formTextOrNull(form, "shelly_ip") }),
    isAddressed: (spec) => Boolean(spec.device_ip),
    // Powercalc reads voltage straight off the device.
    hasVoltageReading: () => true,
    describe: (spec) => ({ source: "Shelly power meter", detail: spec.device_ip }),
  },

  kasa: {
    type: "kasa",
    label: "Kasa smart plug",
    validatable: true,
    discoverable: false,
    supportsDummyLoad: true,
    qualityNote: POLLED_DIRECTLY,
    fromSettings: (settings) => ({ type: "kasa", device_ip: settings?.kasa_ip ?? "" }),
    settingsFromForm: (form) => ({ kasa_ip: formTextOrNull(form, "kasa_ip") }),
    isAddressed: (spec) => Boolean(spec.device_ip),
    hasVoltageReading: () => true,
    describe: (spec) => ({ source: "Kasa power meter", detail: spec.device_ip }),
  },

  dummy: {
    type: "dummy",
    label: "Synthetic test meter",
    validatable: false,
    discoverable: false,
    supportsDummyLoad: false,
    fromSettings: () => ({ type: "dummy" }),
    settingsFromForm: () => ({}),
    isAddressed: () => true,
    hasVoltageReading: () => false,
    describe: () => ({ source: "Synthetic test meter", detail: "No external readings are used." }),
  },
};

/** Meters in picker order, for the settings form to list. See {@link meterFor} on the cast. */
export const POWER_METER_LIST: PowerMeterDescriptor[] = Object.values(POWER_METERS) as PowerMeterDescriptor[];

/** The descriptor for a meter. */
export function meterFor(type: PowerMeterType): PowerMeterDescriptor {
  // Sound because the record is keyed by exactly this union; the cast only drops the per-type spec
  // narrowing, which nothing outside this module needs.
  return POWER_METERS[type] as PowerMeterDescriptor;
}

/** The meter the saved app settings configure. */
export function specFromSettings(settings: AppSettings | undefined, context: MeterContext): PowerMeterSpec {
  return meterFor(settings?.power_meter ?? "hass").fromSettings(settings, context);
}

/** The meter a draft reads from: the one its request already names, else the saved default. */
export function specFromRequest(
  request: MeasurementRequest | undefined,
  settings: AppSettings | undefined,
  context: MeterContext,
): PowerMeterSpec {
  return request?.power_meter ?? specFromSettings(settings, context);
}

/** The settings payload the form describes: the selected meter's keys, and null for the rest. */
export function settingsFromForm(form: FormData): PowerMeterSettings & { power_meter: PowerMeterType } {
  const type = formChoice(form, "power_meter", ["hass", "shelly", "kasa", "dummy"] as const, "hass");
  return {
    power_meter: type,
    default_power_entity_id: null,
    shelly_ip: null,
    kasa_ip: null,
    ...meterFor(type).settingsFromForm(form),
  };
}

/** Whether this meter names a usable address. */
export function isAddressed(spec: PowerMeterSpec): boolean {
  return meterFor(spec.type).isAddressed(spec);
}

/** Whether dummy-load correction can read the voltage it needs from this meter. */
export function hasVoltageReading(spec: PowerMeterSpec): boolean {
  return meterFor(spec.type).hasVoltageReading(spec);
}

/** How the meter is described to the user. */
export function describe(spec: PowerMeterSpec, context: MeterContext): MeterDescription {
  return meterFor(spec.type).describe(spec, context);
}

/** The meter as one line on the review screen, where the entity catalogue is not at hand. */
export function summarize(spec: PowerMeterSpec): string {
  return spec.type === "hass" ? spec.entity_id : meterFor(spec.type).label;
}

/** The voltage sensor Home Assistant associates with a power sensor, when there is one. */
export function relatedVoltageEntityId(powers: EntityDescriptor[], powerEntityId: string): string {
  return powers.find((entity) => entity.entity_id === powerEntityId)?.related_voltage_entity_id ?? "";
}
