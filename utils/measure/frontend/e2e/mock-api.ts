import type { Page, Route } from "@playwright/test";
import type {
  AppSettings,
  Capabilities,
  EntityCatalog,
  EntityDescriptor,
  MeasureDefinition,
  MeasurementParameters,
  PlotCollection,
  PreflightResponse,
  SessionEvent,
  SessionFile,
  SessionSnapshot,
  SessionSummary,
} from "../src/types";

/**
 * A stand-in for the measure backend, served straight into the browser by `page.route`.
 *
 * The fixtures are typed against the app's own `src/types`, so `tsc` fails the moment a
 * response shape drifts from what the client expects. What it cannot catch is the server
 * drifting from those types — that seam stays the job of the Python API tests.
 */

const parameters: MeasurementParameters = {
  sleep_time: 2, sample_count: 1, sleep_time_sample: 1, max_retries: 5, max_nudges: 0,
  bri_bri_steps: 1, ct_bri_steps: 5, ct_mired_steps: 10,
  hs_bri_steps: 32, hs_hue_steps: 2731, hs_sat_steps: 32,
  min_brightness: 1, sleep_initial: 10, sleep_standby: 20,
  effect_bri_steps: 40, measure_time_effect: 180, measure_time_effect_min: 20,
};

const capabilities: Capabilities = {
  runtime_version: "v0.3.0:app",
  defaults: parameters,
  limits: { sleep_time: { min: 0, max: 60 }, sample_count: { min: 1, max: 100 } },
  developer_mode: false,
  fast_test_mode: false,
};

const powers: EntityDescriptor[] = [
  { entity_id: "sensor.plug_power", name: "Plug power", unit: "W", related_voltage_entity_id: "sensor.plug_voltage" },
];
const voltages: EntityDescriptor[] = [{ entity_id: "sensor.plug_voltage", name: "Plug voltage", unit: "V" }];
const lights: EntityDescriptor[] = [{ entity_id: "light.desk", name: "Desk lamp", supported_modes: ["brightness"] }];

const catalog: EntityCatalog = { lights, powers, voltages };

const settings: AppSettings = {
  default_power_entity_id: "sensor.plug_power",
  default_measure_device: "Shelly Plug S",
  power_meter: "hass",
  shelly_ip: null,
  kasa_ip: null,
  fast_test_mode: false,
  measurement_defaults: {
    sleep_time: 2, sample_count: 1, sleep_time_sample: 1, max_retries: 5, max_nudges: 0,
  },
};

/** "Average" is the simplest type the server offers: one duration field and no profile. */
const averageDefinition: MeasureDefinition = {
  measure_type: "average",
  label: "Average",
  description: "Measure average power for a fixed duration.",
  icon: "📊",
  model_id_example: "WSP002",
  product_name_example: "",
  parameters: [
    { name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" },
  ],
  fields: [
    { name: "power_entity_id", role: "power_meter", label: "Power sensor", control: "entity", required: true, options: [] },
    { name: "duration", role: "attribute", label: "Duration (seconds)", control: "number", required: true, options: [], default: 60 },
  ],
  supports_profile: false,
  supports_resume: false,
};

const lightDefinition: MeasureDefinition = {
  measure_type: "light",
  label: "Light bulb(s)",
  description: "Build a lookup-table power profile for a light.",
  icon: "💡",
  model_id_example: "LWA017",
  product_name_example: "Philips Hue White Ambiance A60 E27",
  parameters: [
    { name: "sleep_time", label: "Settle time (seconds)", step: "0.1", group: "Sampling" },
    { name: "bri_bri_steps", label: "Brightness mode step", group: "Profile resolution" },
  ],
  fields: [
    { name: "power_entity_id", role: "power_meter", label: "Power sensor", control: "entity", required: true, entity_domains: ["sensor"], options: [] },
    { name: "light_entity_id", role: "controller", label: "Light", plural_label: "Lights", control: "entity", required: true, multiple: true, entity_domains: ["light"], options: [] },
    {
      name: "modes", role: "attribute", label: "Lookup-table modes", control: "multi_select",
      narrowed_by: "light_entity_id", required: true,
      options: [{ value: "brightness", label: "Brightness", enables: ["bri_bri_steps"] }],
    },
  ],
  supports_profile: true,
  supports_resume: true,
};

const completedSession: SessionSummary = {
  session_id: "session-completed",
  state: "completed",
  created_at: "2026-08-14T09:00:00Z",
  updated_at: "2026-08-14T09:12:00Z",
  measure_type: "light",
  model_id: "LWA017",
  product_name: "Hue White Ambiance A60",
  measure_device: "Shelly Plug S",
  completed: 255,
  total: 255,
  percent: 100,
  can_resume: false,
  file_count: 2,
  size: 4096,
  active: false,
};

const completedSnapshot: SessionSnapshot = {
  session_id: "session-completed",
  state: "completed",
  created_at: completedSession.created_at,
  updated_at: completedSession.updated_at,
  phase: "Measurement complete",
  progress: { completed: 255, total: 255 },
  summary: { "Maximum power": "8.42 W", "Measured points": "255" },
};

/** A light run writes one CSV per lookup-table mode, named after the mode, plus the model. */
const files: SessionFile[] = [
  { name: "brightness.csv", size: 2048, media_type: "text/csv" },
  { name: "model.json", size: 512, media_type: "application/json" },
];

const plots: PlotCollection = {
  partial: false,
  warnings: [],
  plots: [{
    id: "brightness",
    title: "Brightness",
    kind: "line",
    x_label: "Brightness",
    y_label: "Power (W)",
    source: "brightness.csv",
    series: [{ label: "Power", color: "#5488e8", points: [{ x: 1, y: 0.4, color: null }, { x: 255, y: 8.4, color: null }] }],
  }],
};

const preflight: PreflightResponse = {
  valid: true,
  warnings: [],
  estimated_duration_seconds: 60,
  power_meter_diagnostic: {
    success: true,
    power: 8.4,
    status: "good",
    precision_decimals: 2,
    max_report_interval_seconds: 1.8,
    reports_observed: 7,
    duration_seconds: 12,
    precision_status: "good",
    update_interval_status: "good",
    messages: ["The sensor meets the recommended update frequency."],
  },
};

const startedSnapshot: SessionSnapshot = {
  session_id: "session-running",
  state: "running",
  created_at: "2026-08-14T10:00:00Z",
  updated_at: "2026-08-14T10:00:01Z",
  phase: "Measuring average power",
  progress: { completed: 0, total: 1 },
};

/**
 * Events the mocked stream replays once the running view subscribes.
 *
 * Deliberately free of `snapshot`: opening the stream also triggers a snapshot refetch, and a
 * snapshot carried by an event would race with it. Log and sample payloads reach the view only
 * through the stream, so they are what the browser test can assert on unambiguously.
 */
const streamEvents: SessionEvent[] = [
  { sequence: 1, type: "log", data: { message: "Connected to the power meter" } },
  { sequence: 2, type: "sample", data: { power: 8.41 } },
];

/**
 * Server-Sent Events as one complete response body. `page.route` cannot hold a stream open, so
 * the events all arrive at once and the connection then closes; the long `retry` stops
 * `EventSource` from reconnecting for the rest of the test.
 */
function eventStreamBody(events: SessionEvent[]): string {
  const frames = events.map((event) => `event: ${event.type}\ndata: ${JSON.stringify(event)}`);
  return `retry: 3600000\n\n${frames.join("\n\n")}\n\n`;
}

export interface MockApiOptions {
  /** Sessions the app lists on boot. Defaults to the one completed session. */
  sessions?: SessionSummary[];
}

/**
 * Route every API call the app makes to a canned response.
 *
 * Install it before `page.goto`, since the app starts fetching as soon as the shell connects.
 */
export async function mockApi(page: Page, options: MockApiOptions = {}): Promise<void> {
  const sessions = options.sessions ?? [completedSession];

  await page.route("**/api/**", async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^.*\/api\//, "");
    const method = route.request().method();

    const json = (body: unknown) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });

    if (path === "capabilities") return json(capabilities);
    if (path === "entity-catalog") return json(catalog);
    if (path === "settings") return json(settings);
    if (path === "contribution/auth") return json({ connected: false });
    if (path === "contribution/status") return json({ submitted: false });
    if (path === "measure-definitions") return json([averageDefinition, lightDefinition]);
    if (path === "dummy-load/calibration") return json(null);
    if (path === "entities") {
      const domain = url.searchParams.get("domain");
      return json(domain === "light" ? lights : powers);
    }
    if (path === "preflight") return json(preflight);
    if (path === "sessions" && method === "POST") return json(startedSnapshot);
    if (path === "sessions") return json(sessions);
    if (path === "sessions/session-running/events") {
      return route.fulfill({ status: 200, contentType: "text/event-stream", body: eventStreamBody(streamEvents) });
    }
    if (path === "sessions/session-running") return json(startedSnapshot);
    if (path === "sessions/session-completed/files") return json(files);
    if (path === "sessions/session-completed/plots") return json(plots);
    if (path === "sessions/session-completed/contribution") return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ code: "not_found", message: "No draft", field: null }) });
    if (path === "sessions/session-completed") return json(completedSnapshot);

    // Fail loudly rather than silently hanging: an unrouted call means the app grew a
    // dependency this mock does not know about.
    return route.fulfill({ status: 501, contentType: "application/json", body: JSON.stringify({ code: "not_mocked", message: `No mock for ${method} ${path}`, field: null }) });
  });
}

export { completedSession, settings, startedSnapshot };
