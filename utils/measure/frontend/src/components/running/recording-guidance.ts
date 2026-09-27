import type { MeasurementRequest } from "../../types";

const START = "Start recording while the device is in a stable idle or standby state, before changing its mode.";
const FINISH = "Keep each state long enough for several power samples. Return to idle, then stop recording; repeat important states in another run.";
const GENERIC_ACTIONS = ["Switch through the device's distinct idle and active modes, and any relevant output settings."];

const DEVICE_ACTIONS: Record<string, string[]> = {
  air_purifier: ["Switch through low, medium, high, and automatic modes if available."],
  camera: ["Capture idle, live viewing, recording, and night or infrared mode if available."],
  cover: ["Open the cover fully, leave it open, then close it. Repeat the cycle and pause partway if supported."],
  fan: ["Switch through off and several stable fan speeds, including any automatic mode."],
  generic_iot: GENERIC_ACTIONS,
  heating: ["Capture idle and active heating, then change between eco, normal, or boost modes if available."],
  humidifier: ["Switch through off, low, and high output, plus automatic mode if available."],
  lawn_mower_robot: ["Record the docked state, a mowing run, the return to dock, and charging until idle again."],
  network: ["Capture idle network traffic and a sustained high-traffic workload, then return to idle."],
  power_meter: ["Leave the meter output empty: no load should be connected. Change its display or relay modes to measure the meter's own consumption."],
  printer: ["Capture ready, printing, scanning or copying, and sleep states if available."],
  set_top_box: ["Capture standby, startup, live viewing, streaming or menu use, then return to standby."],
  smart_dimmer: ["Leave the dimmer output empty: no load should be connected. Move from off through low, medium, and high settings to measure the dimmer's own consumption."],
  smart_switch: ["Leave the switch output empty: no load should be connected. Switch it off and on several times to measure the switch's own consumption."],
  television: ["Capture standby, normal viewing, and other modes you use, such as streaming or HDR."],
  ups: ["Keep the connected load stable while recording idle, charging, and battery operation if available."],
  water_heater: ["Capture idle and a full heating cycle until the target temperature is reached."],
};

/** Give the operator a practical sequence before a complex-profile recording begins. */
export function recordingGuidance(request: MeasurementRequest | undefined): string[] | undefined {
  if (request?.measure_type !== "recorder" || request.recorder_purpose !== "complex_profile") return undefined;
  if (request.profile_recipe === "vacuum_robot") {
    return [
      "Measure the entire dock at the wall outlet. Start recording before docking a low-battery vacuum or starting a cleaning run.",
      "Run a cleaning trip and return to the dock. Include emptying, mop washing, and drying if supported; let each activity finish.",
      "Keep recording through charging over at least 20 battery percentage points, ideally until full and the dock returns to idle. Then stop recording.",
      "Use Record more for another complete cycle. Independent runs help validate the profile.",
    ];
  }

  const actions = DEVICE_ACTIONS[request.profile_device_type ?? "generic_iot"] ?? GENERIC_ACTIONS;
  return [START, ...actions, FINISH];
}
