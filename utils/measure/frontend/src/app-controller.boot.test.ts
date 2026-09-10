import { MeasureAppController } from "./app-controller";
import type { SessionEvent } from "./types";
import { api, connection, sessionSummary, state } from "./testing/controller";

describe("measure app controller: boot", () => {
  it("boots core data and lazily fetches entities for the selected measurement", async () => {
    const requestedDomains: string[] = [];
    let catalogCalls = 0;
    let deviceClassCalls = 0;
    const appState = state();
    const appApi = api({
      getEntityCatalog: async () => {
        catalogCalls += 1;
        return {
          lights: [{ entity_id: "light.desk", name: "Desk" }],
          powers: [{ entity_id: "sensor.plug_power", name: "Plug power" }],
          voltages: [{ entity_id: "sensor.plug_voltage", name: "Plug voltage" }],
        };
      },
      getMeasureDefinitions: async () => [{
        measure_type: "fan",
    icon: "🌀",
    model_id_example: "WSP002",
    product_name_example: "",
    parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }], label: "Fan", description: "Measure fan power.", supports_profile: true, supports_resume: false,
        fields: [{ name: "fan_entity_id", role: "controller", label: "Fan", control: "entity", required: true, entity_domains: ["fan"], options: [] }],
      }],
      getEntitiesByDomain: async (domain) => {
        requestedDomains.push(domain);
        return [{ entity_id: "fan.bedroom", name: "Bedroom fan" }];
      },
      getEntitiesByDeviceClass: async () => {
        deviceClassCalls += 1;
        return [];
      },
    });
    const controller = new MeasureAppController(appState, () => appApi, () => connection(), () => undefined);

    await controller.boot();
    expect(appState.view).toBe("sessions");
    expect(catalogCalls).toBe(1);
    expect(appState.lights[0]?.entity_id).toBe("light.desk");
    expect(appState.powers[0]?.entity_id).toBe("sensor.plug_power");
    expect(appState.voltages[0]?.entity_id).toBe("sensor.plug_voltage");
    expect(requestedDomains).toEqual([]);
    expect(deviceClassCalls).toBe(0);

    controller.selectMeasureType("fan");
    expect(appState.selectedMeasureType).toBe("fan");
    await vi.waitFor(() => expect(appState.deviceEntities.fan?.[0]?.entity_id).toBe("fan.bedroom"));
    expect(requestedDomains).toEqual(["fan"]);
  });

  it("loads the complete entity catalog for a recorder definition that requests it", async () => {
    let allCalls = 0;
    const appState = state();
    const appApi = api({
      getMeasureDefinitions: async () => [{
        measure_type: "recorder", icon: "⏺", model_id_example: "", product_name_example: "", parameters: [],
        label: "Recorder", description: "Record entity states.", supports_profile: false, supports_resume: false,
        fields: [{ name: "tracked_entity_ids", role: "attribute", label: "Tracked entities", control: "entity", required: true, multiple: true, all_entities: true, options: [] }],
      }],
      getAllEntities: async () => {
        allCalls += 1;
        return [{ entity_id: "climate.room", name: "Room", domain: "climate" }];
      },
    });
    const controller = new MeasureAppController(appState, () => appApi, () => connection(), () => undefined);

    await controller.boot();
    controller.selectMeasureType("recorder");

    await vi.waitFor(() => expect(appState.deviceEntities["*"]?.[0]?.entity_id).toBe("climate.room"));
    expect(allCalls).toBe(1);
  });

  it("loads the all-entity catalog a duplicated session's own purpose makes visible", async () => {
    let allCalls = 0;
    const appState = state();
    const appApi = api({
      getMeasureDefinitions: async () => [{
        measure_type: "recorder", icon: "⏺", model_id_example: "", product_name_example: "", parameters: [],
        label: "Recorder", description: "Record entity states.", supports_profile: false, supports_resume: false,
        fields: [
          {
            name: "recorder_purpose", role: "attribute", label: "Purpose", control: "select", required: true,
            default: "playbook",
            options: [{ value: "playbook", label: "Playbook" }, { value: "complex_profile", label: "Complex profile" }],
          },
          {
            name: "tracked_entity_ids", role: "attribute", label: "Tracked entities", control: "entity", required: true,
            multiple: true, all_entities: true, options: [], visible_when: { recorder_purpose: ["complex_profile"] },
          },
        ],
      }],
      getSession: async () => ({
        state: "completed",
        session_id: "session-1",
        request: { measure_type: "recorder", recorder_purpose: "complex_profile", tracked_entity_ids: ["climate.room"] },
      }) as never,
      getAllEntities: async () => {
        allCalls += 1;
        return [{ entity_id: "climate.room", name: "Room", domain: "climate" }];
      },
    });
    const controller = new MeasureAppController(appState, () => appApi, () => connection(), () => undefined);

    await controller.boot();
    await controller.duplicateSession("session-1");

    // The type's own default purpose hides the field; only the stored request reveals it.
    expect(allCalls).toBe(1);
    expect(appState.deviceEntities["*"]?.[0]?.entity_id).toBe("climate.room");
  });

  it("retains entity discovery errors and updates session state from the event port", async () => {
    let onEvent: ((event: SessionEvent) => void) | undefined;
    const appState = state();
    const appApi = api({
      getSessions: async () => [sessionSummary({ state: "running", active: true, percent: 50 })],
      getSession: async () => ({ state: "running", session_id: "session-1" }),
      getMeasureDefinitions: async () => [{
        measure_type: "fan",
    icon: "🌀",
    model_id_example: "WSP002",
    product_name_example: "",
    parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }], label: "Fan", description: "Measure fan power.", supports_profile: true, supports_resume: false,
        fields: [{ name: "fan_entity_id", role: "controller", label: "Fan", control: "entity", required: true, entity_domains: ["fan"], options: [] }],
      }],
      getEntitiesByDomain: async (domain) => {
        if (domain === "fan") throw new Error("Entity API failed");
        return [];
      },
    });
    const controller = new MeasureAppController(appState, () => appApi, (_sessionId, callbacks) => {
      onEvent = callbacks.onEvent;
      return connection();
    }, () => undefined);

    await controller.boot();
    controller.selectMeasureType("fan");
    await vi.waitFor(() => expect(appState.deviceEntityErrors.fan).toBe("Entity API failed"));

    onEvent?.({ sequence: 1, type: "sample", data: { power: 12.5 }, snapshot: { state: "running" } });
    expect(appState.samples).toEqual([12.5]);

    const warning = "Discarding measurement: 0 watt was read from the power meter";
    onEvent?.({ sequence: 2, type: "warning", data: { message: warning }, snapshot: { state: "running", warnings: [warning] } });
    expect(appState.logs).toEqual([warning]);
  });


});
