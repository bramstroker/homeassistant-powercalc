import type { MeasurementRequest } from "../../types";
import { isVacuumProfileRequest } from "../../measurement/definition";

const START = "Start recording with the device powered and in a stable state, before changing its settings.";
const FINISH = "Keep every state long enough for at least five power samples. Return to the starting state, then stop recording.";
const REPEAT = "Use Record more for a second, separate run. Repeat every state, with at least five samples per state in both runs, so PowerCalc can check that the power measurements repeat reliably.";
const GENERIC_ACTIONS = ["Switch through the device's distinct idle and active modes, and any relevant output settings."];

const DEVICE_ACTIONS: Record<string, string[]> = {
  air_purifier: [
    "Record off and each manual fan speed reported in Home Assistant. Let the power settle at each speed; disable automatic modes that change the speed on their own.",
    "Keep the display, ionizer, and other extra functions at the same settings throughout both runs. Their separate power contributions are not modelled by this recording.",
  ],
  camera: [
    "Check that the camera's recorded state or attributes, or a selected additional day/night or infrared entity, distinguish infrared off from on. Without that signal, the recorder cannot create an infrared-dependent profile.",
    "Record with infrared off and then on, allowing the power to settle in each state. You can change the infrared setting or lighting conditions; verify that the recorded signal follows the actual infrared state. Keep other camera settings unchanged.",
  ],
  fan: [
    "Record off and each manual speed reported in Home Assistant. Disable automatic modes so each speed stays steady while it is measured.",
    "Keep oscillation, direction, lights, and other extra functions at the same settings throughout both runs. This recording models the selected speed or state, not combinations of those functions.",
  ],
  heating: [
    "Record standby and each heating power level reported in Home Assistant, such as numbered fan or heating modes. Let the power settle at each level.",
    "Check that the recorded states distinguish active heating from thermostat idle periods. Changing only the target temperature is not a reliable indication of the power being used.",
  ],
  printer: [
    "Select the printer status entity that reports ready, printing, and sleep. Record those states, using the same representative print job in both runs.",
    "Include scanning or copying only if Home Assistant reports them as distinct states. Use a long enough job to collect at least five samples while printing.",
  ],
  set_top_box: [
    "Record the box switched on during normal viewing, then in standby. Keep its energy-saving or standby mode unchanged throughout both runs.",
    "Allow startup and standby transitions to finish so you capture stable power in each state. Check that the media player entity reports the on and standby states correctly.",
  ],
};

/** Give the operator a practical sequence before a complex-profile recording begins. */
export function recordingGuidance(request: MeasurementRequest | undefined): string[] | undefined {
  if (request?.measure_type !== "recorder" || request.recorder_purpose !== "complex_profile") return undefined;
  if (isVacuumProfileRequest(request)) {
    return [
      "Measure the entire dock at the wall outlet. This measures mains power used by the dock, including charging. Start recording before docking a low-battery vacuum or starting a cleaning run.",
      "Run a cleaning trip and return to the dock. Include emptying, mop washing, and drying if supported; let each activity finish.",
      "Keep recording through charging over at least 20 battery percentage points, ideally until full and the dock returns to idle. Then stop recording.",
      "Use Record more for another complete cycle, repeating every dock activity and charging over a similar battery range. Independent cycles help validate the profile.",
    ];
  }

  const actions = DEVICE_ACTIONS[request.profile_device_type ?? "generic_iot"] ?? GENERIC_ACTIONS;
  return [START, ...actions, FINISH, REPEAT];
}
