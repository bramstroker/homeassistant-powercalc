from dataclasses import dataclass
from enum import StrEnum

from measure.const import MEASURE_TYPE_LABELS, MeasureType
from measure.controller.charging.const import ChargingDeviceType
from measure.controller.charging.spec import charging_entity_domain
from measure.controller.light.const import LutMode
from measure.request import RecorderProfileRecipe, RecorderPurpose


class FieldControl(StrEnum):
    ENTITY = "entity"
    NUMBER = "number"
    TEXT = "text"
    BOOLEAN = "boolean"
    SELECT = "select"
    MULTI_SELECT = "multi_select"


class FieldRole(StrEnum):
    """Where a submitted field value lands in the measurement request.

    Clients build the request from this alone: a CONTROLLER field becomes the
    discriminated ``controller`` spec, POWER_METER is supplied by the client's own
    power-meter configuration, and an ATTRIBUTE sets the request attribute that
    carries the same name as the field.
    """

    ATTRIBUTE = "attribute"
    CONTROLLER = "controller"
    POWER_METER = "power_meter"


@dataclass(frozen=True)
class FieldOption:
    value: str
    label: str
    entity_domain: str | None = None
    #: Measurement parameters that only apply while this option is selected.
    enables: tuple[str, ...] = ()
    description: str = ""
    guidance: tuple[str, ...] = ()


@dataclass(frozen=True)
class FormFieldDefinition:
    name: str
    label: str
    control: FieldControl
    role: FieldRole = FieldRole.ATTRIBUTE
    #: Field whose current value constrains this one. A multi-select names the controller field
    #: whose entity limits its options; an entity field names the select whose chosen option
    #: supplies the entity domain to offer.
    narrowed_by: str | None = None
    required: bool = True
    entity_domains: tuple[str, ...] = ()
    options: tuple[FieldOption, ...] = ()
    default: str | int | bool | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    #: Whether several entities can be selected for this field at once.
    multiple: bool = False
    #: Label to use while several entities are selected.
    plural_label: str = ""
    #: Entity field whose number of selected entities this count follows by default.
    derived_from: str | None = None
    hint: str = ""
    #: Other field values required for this field to be shown.
    visible_when: tuple[tuple[str, tuple[str, ...]], ...] = ()
    #: Load the full Home Assistant entity catalog rather than one supported controller domain.
    all_entities: bool = False
    entity_device_classes: tuple[str, ...] = ()
    #: Entity field whose Home Assistant device should be preferred or required.
    related_to: str | None = None
    same_device_only: bool = False
    #: Restate this field on the review screen.
    review: bool = False


@dataclass(frozen=True)
class ParameterDefinition:
    """A measurement tuning parameter as one measure type presents it.

    The same parameter can read differently per type — a light settles, a recorder
    samples — so the wording lives here rather than in the client. Bounds come from
    ``PARAMETER_LIMITS`` via the capabilities endpoint.
    """

    name: str
    label: str
    hint: str = ""
    step: str = "1"
    #: Heading this parameter is grouped under, repeated on each member of the group.
    group: str = ""
    #: Only applies while the named parameter is greater than one.
    requires_multiple: str | None = None


@dataclass(frozen=True)
class MeasurementDefinition:
    measure_type: MeasureType
    description: str
    icon: str
    confirmation_action: str | None = None
    #: Present the confirmation as a warning, for a measurement that makes noise or mess.
    confirmation_is_warning: bool = False
    #: Placeholders steering the profile fields, taken from real entries in the profile library.
    model_id_example: str = ""
    product_name_example: str = ""
    fields: tuple[FormFieldDefinition, ...] = ()
    #: Tuning parameters this measure type exposes, in the order they are shown.
    parameters: tuple[ParameterDefinition, ...] = ()
    supports_profile: bool = True
    supports_resume: bool = False

    @property
    def label(self) -> str:
        return MEASURE_TYPE_LABELS[self.measure_type]


def _controller(
    name: str,
    label: str,
    *domains: str,
    narrowed_by: str | None = None,
    multiple: bool = False,
    plural_label: str = "",
) -> FormFieldDefinition:
    """Entity field that selects the device being measured, and becomes the request controller."""
    return FormFieldDefinition(
        name=name,
        label=label,
        control=FieldControl.ENTITY,
        role=FieldRole.CONTROLLER,
        narrowed_by=narrowed_by,
        entity_domains=domains,
        multiple=multiple,
        plural_label=plural_label,
    )


#: The lookup-table modes a light can be profiled in, each with the resolution parameters it
#: activates. A light only offers the subset its entity reports as supported.
LIGHT_MODE_OPTIONS = (
    FieldOption(value=LutMode.BRIGHTNESS, label="Brightness", enables=("bri_bri_steps",)),
    FieldOption(value=LutMode.COLOR_TEMP, label="Color temperature", enables=("ct_bri_steps", "ct_mired_steps")),
    FieldOption(value=LutMode.HS, label="Hue & saturation", enables=("hs_bri_steps", "hs_hue_steps", "hs_sat_steps")),
    FieldOption(
        value=LutMode.EFFECT,
        label="Effect",
        enables=("effect_bri_steps", "measure_time_effect_min", "measure_time_effect"),
    ),
)

MODES_FIELD = FormFieldDefinition(
    name="modes",
    label="Lookup-table modes",
    control=FieldControl.MULTI_SELECT,
    narrowed_by="light_entity_id",
    options=LIGHT_MODE_OPTIONS,
)

SAMPLING = "Sampling"
RESOLUTION = "Profile resolution"


def _sampling(label: str, hint: str) -> tuple[ParameterDefinition, ...]:
    """Repeated-reading parameters, worded for the type that takes the readings."""
    return (
        ParameterDefinition(name="sample_count", label=label, hint=hint, group=SAMPLING),
        ParameterDefinition(
            name="sleep_time_sample",
            label="Time between samples (seconds)",
            hint="Only used when taking more than one sample.",
            group=SAMPLING,
            requires_multiple="sample_count",
        ),
    )


READING_INTERVAL = ParameterDefinition(
    name="sleep_time",
    label="Reading interval (seconds)",
    hint="Delay between repeated power readings and retries.",
    step="0.1",
    group=SAMPLING,
)

POINT_SAMPLING = _sampling("Samples per reading", "More samples reduce noise but increase measurement time.")

LIGHT_PARAMETERS = (
    ParameterDefinition(
        name="sleep_time",
        label="Settle time (seconds)",
        hint="Wait after changing the light before reading power.",
        step="0.1",
        group=SAMPLING,
    ),
    *_sampling("Samples per point", "More samples reduce noise but increase measurement time."),
    ParameterDefinition(
        name="min_brightness",
        label="Minimum brightness",
        hint="Increase this when the light does not turn on at its lowest level.",
        group=SAMPLING,
    ),
    ParameterDefinition(name="sleep_initial", label="Initial stabilization (seconds)", group=SAMPLING),
    ParameterDefinition(name="sleep_standby", label="Standby stabilization (seconds)", group=SAMPLING),
    ParameterDefinition(
        name="bri_bri_steps",
        label="Brightness mode step",
        hint="Native brightness increment (1–255).",  # noqa: RUF001
        group=RESOLUTION,
    ),
    ParameterDefinition(
        name="ct_bri_steps",
        label="Color temperature brightness step",
        hint="Native brightness increment used while measuring color temperature.",
        group=RESOLUTION,
    ),
    ParameterDefinition(
        name="ct_mired_steps",
        label="Color temperature mired step",
        hint="Native color-temperature increment in mired.",
        group=RESOLUTION,
    ),
    ParameterDefinition(
        name="hs_bri_steps",
        label="HS brightness step",
        hint="Native brightness increment used for hue and saturation.",
        group=RESOLUTION,
    ),
    ParameterDefinition(
        name="hs_hue_steps",
        label="HS hue step",
        hint="Native Home Assistant hue increment (0–65535).",  # noqa: RUF001
        group=RESOLUTION,
    ),
    ParameterDefinition(
        name="hs_sat_steps",
        label="HS saturation step",
        hint="Native saturation increment (1–255).",  # noqa: RUF001
        group=RESOLUTION,
    ),
    ParameterDefinition(
        name="effect_bri_steps",
        label="Effect brightness step",
        hint="Native brightness increment between long-running effect samples.",
        group=RESOLUTION,
    ),
    ParameterDefinition(
        name="measure_time_effect_min",
        label="Minimum time per effect (seconds)",
        hint="An effect can stop after this time once its average converges.",
        group=RESOLUTION,
    ),
    ParameterDefinition(
        name="measure_time_effect",
        label="Maximum time per effect (seconds)",
        hint="Upper time limit for every effect and brightness combination.",
        group=RESOLUTION,
    ),
)

POWER_FIELD = FormFieldDefinition(
    name="power_entity_id",
    label="Power sensor",
    control=FieldControl.ENTITY,
    role=FieldRole.POWER_METER,
    entity_domains=("sensor",),
)

MEASUREMENT_REGISTRY: dict[MeasureType, MeasurementDefinition] = {
    MeasureType.LIGHT: MeasurementDefinition(
        measure_type=MeasureType.LIGHT,
        description="Build a lookup-table power profile for a light.",
        icon="💡",
        model_id_example="LWA017",
        product_name_example="Hue White Ambiance A60 E27",
        parameters=LIGHT_PARAMETERS,
        fields=(
            POWER_FIELD,
            _controller("light_entity_id", "Light", "light", multiple=True, plural_label="Lights"),
            MODES_FIELD,
            FormFieldDefinition(
                name="multiple_light_count",
                label="Number of lights",
                control=FieldControl.NUMBER,
                default=1,
                minimum=1,
                maximum=100,
                derived_from="light_entity_id",
                hint="Total number of identical physical lights; measured power is divided by this value.",
            ),
        ),
        supports_resume=True,
    ),
    MeasureType.SPEAKER: MeasurementDefinition(
        measure_type=MeasureType.SPEAKER,
        description="Measure power across media-player volume levels.",
        icon="🔊",
        model_id_example="B7W64E",
        product_name_example="Amazon Echo Dot (Gen4)",
        confirmation_action="Start speaker measurement",
        confirmation_is_warning=True,
        parameters=(
            READING_INTERVAL,
            ParameterDefinition(name="sleep_standby", label="Standby stabilization (seconds)", group=SAMPLING),
        ),
        fields=(
            POWER_FIELD,
            _controller("media_player_entity_id", "Media player", "media_player"),
            FormFieldDefinition(
                name="disable_streaming",
                label="Disable automatic pink-noise streaming",
                control=FieldControl.BOOLEAN,
                required=False,
                default=False,
            ),
        ),
    ),
    MeasureType.RECORDER: MeasurementDefinition(
        measure_type=MeasureType.RECORDER,
        description="Record power readings, optionally together with Home Assistant entity states.",
        icon="⏺",
        confirmation_action="Start recording",
        parameters=(READING_INTERVAL, *POINT_SAMPLING),
        fields=(
            POWER_FIELD,
            FormFieldDefinition(
                name="recorder_purpose",
                label="What do you want to create?",
                control=FieldControl.SELECT,
                options=(
                    FieldOption(
                        value=RecorderPurpose.PLAYBOOK,
                        label="A Playbook CSV",
                        description="Record power readings in the two-column format used to build a playbook.",
                    ),
                    FieldOption(
                        value=RecorderPurpose.COMPLEX_PROFILE,
                        label="Data for a complex power profile (experimental)",
                        description=(
                            "This experimental workflow records JSON Lines source data and can create a fixed "
                            "states_power model when one state or attribute clearly explains power. Composite models "
                            "are not supported yet, so the workflow is not feature complete. Hold every relevant "
                            "device state for at least five samples."
                        ),
                    ),
                ),
                default=RecorderPurpose.PLAYBOOK,
                review=True,
            ),
            FormFieldDefinition(
                name="profile_recipe",
                label="Device type",
                control=FieldControl.SELECT,
                options=(
                    FieldOption(
                        value=RecorderProfileRecipe.GENERIC,
                        label="Generic device",
                        description="Choose the entities whose states may explain changes in power.",
                    ),
                    FieldOption(
                        value=RecorderProfileRecipe.VACUUM_ROBOT,
                        label="Robot vacuum",
                        description="Capture the vacuum, its battery level, and optional dock or feature entities.",
                        guidance=(
                            "Measure the complete dock or base station at the wall outlet.",
                            "Include a low-battery charging cycle and idle and cleaning states.",
                            "Also capture washing, drying, and dust-emptying when the dock supports them.",
                        ),
                    ),
                ),
                default=RecorderProfileRecipe.GENERIC,
                visible_when=(("recorder_purpose", (RecorderPurpose.COMPLEX_PROFILE,)),),
                review=True,
            ),
            FormFieldDefinition(
                name="tracked_entity_ids",
                label="Tracked entity",
                plural_label="Tracked entities",
                control=FieldControl.ENTITY,
                multiple=True,
                all_entities=True,
                visible_when=(
                    ("recorder_purpose", (RecorderPurpose.COMPLEX_PROFILE,)),
                    ("profile_recipe", (RecorderProfileRecipe.GENERIC,)),
                ),
                hint="Select at least one entity whose state or attributes may explain the device's power use.",
                review=True,
            ),
            FormFieldDefinition(
                name="vacuum_entity_id",
                label="Vacuum",
                control=FieldControl.ENTITY,
                entity_domains=("vacuum",),
                all_entities=True,
                visible_when=(
                    ("recorder_purpose", (RecorderPurpose.COMPLEX_PROFILE,)),
                    ("profile_recipe", (RecorderProfileRecipe.VACUUM_ROBOT,)),
                ),
                review=True,
            ),
            FormFieldDefinition(
                name="battery_entity_id",
                label="Battery level sensor",
                control=FieldControl.ENTITY,
                entity_device_classes=("battery",),
                all_entities=True,
                related_to="vacuum_entity_id",
                same_device_only=True,
                visible_when=(
                    ("recorder_purpose", (RecorderPurpose.COMPLEX_PROFILE,)),
                    ("profile_recipe", (RecorderProfileRecipe.VACUUM_ROBOT,)),
                ),
                hint=(
                    "PowerCalc vacuum profiles require a numeric battery percentage sensor on the same Home Assistant "
                    "device."
                ),
                review=True,
            ),
            FormFieldDefinition(
                name="additional_entity_ids",
                label="Additional entity",
                plural_label="Additional entities (optional)",
                control=FieldControl.ENTITY,
                required=False,
                multiple=True,
                all_entities=True,
                related_to="vacuum_entity_id",
                visible_when=(
                    ("recorder_purpose", (RecorderPurpose.COMPLEX_PROFILE,)),
                    ("profile_recipe", (RecorderProfileRecipe.VACUUM_ROBOT,)),
                ),
                hint=(
                    "Entities from the vacuum's device are listed first. You can also choose an entity from elsewhere."
                ),
                review=True,
            ),
        ),
        supports_profile=False,
    ),
    MeasureType.AVERAGE: MeasurementDefinition(
        measure_type=MeasureType.AVERAGE,
        description="Measure average power for a fixed duration.",
        icon="📊",
        confirmation_action="Start averaging",
        parameters=(READING_INTERVAL,),
        fields=(
            POWER_FIELD,
            FormFieldDefinition(
                name="duration",
                label="Duration (seconds)",
                control=FieldControl.NUMBER,
                default=60,
                minimum=1,
                maximum=86_400,
            ),
        ),
        supports_profile=False,
    ),
    MeasureType.CHARGING: MeasurementDefinition(
        measure_type=MeasureType.CHARGING,
        description="Measure charging power against battery level.",
        icon="🔋",
        model_id_example="s6_maxv",
        product_name_example="Roborock S6 MaxV",
        confirmation_action="Start charging measurement",
        parameters=(READING_INTERVAL, *POINT_SAMPLING),
        fields=(
            POWER_FIELD,
            FormFieldDefinition(
                name="charging_device_type",
                label="Charging device type",
                control=FieldControl.SELECT,
                options=(
                    FieldOption(
                        value=ChargingDeviceType.VACUUM_ROBOT,
                        label="Vacuum robot",
                        entity_domain=charging_entity_domain(ChargingDeviceType.VACUUM_ROBOT),
                    ),
                    FieldOption(
                        value=ChargingDeviceType.LAWN_MOWER_ROBOT,
                        label="Lawn mower robot",
                        entity_domain=charging_entity_domain(ChargingDeviceType.LAWN_MOWER_ROBOT),
                    ),
                ),
            ),
            _controller(
                "charging_entity_id",
                "Charging device",
                *(charging_entity_domain(device_type) for device_type in ChargingDeviceType),
                narrowed_by="charging_device_type",
            ),
        ),
    ),
    MeasureType.FAN: MeasurementDefinition(
        measure_type=MeasureType.FAN,
        description="Measure fan power across percentage levels.",
        icon="🌀",
        model_id_example="TP07",
        product_name_example="Dyson Purifier Cool TP07",
        parameters=(READING_INTERVAL,),
        fields=(POWER_FIELD, _controller("fan_entity_id", "Fan", "fan")),
    ),
}


def measurement_definitions() -> tuple[MeasurementDefinition, ...]:
    return tuple(MEASUREMENT_REGISTRY.values())
