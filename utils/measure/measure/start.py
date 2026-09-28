from dataclasses import dataclass

from measure.const import MeasureType


@dataclass(frozen=True)
class MeasurementStart:
    """The operator checkpoint shown before a measurement runner starts."""

    action: str
    message: str
    guidance: tuple[str, ...] = ()
    is_warning: bool = False
    eyebrow: str = "Preparation complete"
    title: str = "Everything is ready"
    guidance_title: str = "Before starting"
    guidance_label: str = "Measurement guidance"


MEASUREMENT_STARTS: dict[MeasureType, MeasurementStart] = {
    MeasureType.LIGHT: MeasurementStart(
        action="Start light measurement",
        message="Ready to measure the light. PowerCalc will control the selected light settings after you start.",
        guidance=(
            (
                "Disable automations and other controls for the selected lights so they cannot change them "
                "during measurement."
            ),
            (
                "PowerCalc will control the lights automatically and cycle through the settings selected for this run "
                "(brightness, color temperature, color, or effects). Keep the lights powered until the measurement "
                "finishes."
            ),
        ),
    ),
    MeasureType.SPEAKER: MeasurementStart(
        action="Start speaker measurement",
        message="Speaker measurements can become very loud at higher volume levels. "
        "Wear hearing protection or move to another room before starting.",
        is_warning=True,
        eyebrow="High volume warning",
        title="Protect your hearing",
        guidance=(
            (
                "PowerCalc will change the speaker volume through the selected levels while test audio plays. "
                "If automatic playback is disabled, start the test audio yourself."
            ),
            "Disable automations and other controls that could change playback or volume during measurement.",
        ),
    ),
    MeasureType.RECORDER: MeasurementStart(
        action="Start recording",
        message="Ready to start recording. Stop the measurement when you are finished.",
        guidance_title="What to record",
        guidance_label="Recording guidance",
    ),
    MeasureType.AVERAGE: MeasurementStart(
        action="Start averaging",
        message="Ready to start the average measurement.",
    ),
    MeasureType.CHARGING: MeasurementStart(
        action="Start charging measurement",
        message="Ready to start charging measurement.",
        guidance=(
            (
                "Measure the complete charging dock at the wall outlet. This captures mains power used for charging "
                "and by the dock; it does not measure the robot's battery use while cleaning or mowing."
            ),
            (
                "Start with the battery as close to empty as possible. Start the measurement before docking the robot, "
                "then let it charge to full without interruption. Leave it docked until the measurement finishes; "
                "PowerCalc also measures trickle charging for 30 minutes after it reaches full charge."
            ),
            "Keep other dock functions, such as washing or drying, off during the charging measurement.",
        ),
    ),
    MeasureType.FAN: MeasurementStart(
        action="Start fan measurement",
        message="Ready to measure the fan. PowerCalc will control the selected fan speeds after you start.",
        guidance=(
            (
                "Disable automations and other controls for the selected fan so they cannot change its speed "
                "during measurement."
            ),
            (
                "Use manual speed mode and keep oscillation, direction, lights, and other extra functions at the same "
                "settings throughout the measurement. The resulting curve describes those settings."
            ),
            (
                "PowerCalc will control the fan automatically, cycling from low to high speed. "
                "Keep the fan powered until the measurement finishes."
            ),
        ),
    ),
}
