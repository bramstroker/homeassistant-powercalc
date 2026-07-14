import { MeasureAppController } from "./app-controller";
import type { EventConnection, MeasureAppApi, MeasureAppState } from "./app-controller";
import type { SessionEvent } from "./types";

const settings = { default_power_entity_id: null, default_measure_device: null, power_meter: "hass" as const, shelly_ip: null };
const capabilities = {
  modes: ["brightness" as const],
  defaults: { sleep_time: 1, sample_count: 2, brightness_step: 5, hue_step: 10, saturation_step: 10, color_temp_step: 5 },
};

function state(): MeasureAppState {
  return {
    view: "loading", errorMessage: "", busy: false, connectedToEvents: false,
    files: [], logs: [], samples: [], lights: [], powers: [], voltages: [], definitions: [],
    deviceEntities: {}, deviceEntityErrors: {}, testingPowerMeter: false,
  };
}

function api(overrides: Partial<MeasureAppApi> = {}): MeasureAppApi {
  return {
    getCapabilities: async () => capabilities,
    getMeasureDefinitions: async () => [],
    getSettings: async () => settings,
    saveSettings: async (value) => value,
    testPowerMeter: async () => ({ success: true, power: 1 }),
    getEntitiesByDomain: async () => [],
    getEntitiesByDeviceClass: async () => [],
    preflight: async () => ({ valid: true, warnings: [] }),
    start: async () => ({ state: "running" }),
    getCurrent: async () => ({ state: "idle" }),
    cancel: async () => ({ state: "cancelled" }),
    confirm: async () => ({ state: "running" }),
    resume: async () => ({ state: "running" }),
    getFiles: async () => [],
    ...overrides,
  };
}

describe("measure app controller", () => {
  it("boots core data and lazily fetches entities for the selected measurement", async () => {
    const requestedDomains: string[] = [];
    const appState = state();
    const appApi = api({
      getMeasureDefinitions: async () => [{
        measure_type: "fan", label: "Fan", description: "Measure fan power.", supports_profile: true, supports_resume: false,
        fields: [{ name: "fan_entity_id", label: "Fan", control: "entity", required: true, entity_domain: "fan", options: [] }],
      }],
      getEntitiesByDomain: async (domain) => {
        requestedDomains.push(domain);
        return [{ entity_id: "fan.bedroom", name: "Bedroom fan" }];
      },
    });
    const controller = new MeasureAppController(appState, () => appApi, () => connection(), () => undefined);

    await controller.boot();
    expect(appState.view).toBe("setup");
    expect(requestedDomains).toEqual(["light"]);

    controller.selectMeasureType("fan");
    await vi.waitFor(() => expect(appState.deviceEntities.fan?.[0]?.entity_id).toBe("fan.bedroom"));
    expect(requestedDomains).toEqual(["light", "fan"]);
  });

  it("retains entity discovery errors and updates session state from the event port", async () => {
    let onEvent: ((event: SessionEvent) => void) | undefined;
    const appState = state();
    const appApi = api({
      getCurrent: async () => ({ state: "running" }),
      getMeasureDefinitions: async () => [{
        measure_type: "fan", label: "Fan", description: "Measure fan power.", supports_profile: true, supports_resume: false,
        fields: [{ name: "fan_entity_id", label: "Fan", control: "entity", required: true, entity_domain: "fan", options: [] }],
      }],
      getEntitiesByDomain: async (domain) => {
        if (domain === "fan") throw new Error("Entity API failed");
        return [];
      },
    });
    const controller = new MeasureAppController(appState, () => appApi, (callbacks) => {
      onEvent = callbacks.onEvent;
      return connection();
    }, () => undefined);

    await controller.boot();
    controller.selectMeasureType("fan");
    await vi.waitFor(() => expect(appState.deviceEntityErrors.fan).toBe("Entity API failed"));

    onEvent?.({ sequence: 1, type: "sample", data: { power: 12.5 }, snapshot: { state: "running" } });
    expect(appState.samples).toEqual([12.5]);
  });
});

function connection(): EventConnection {
  return { connect: () => undefined, close: () => undefined };
}
