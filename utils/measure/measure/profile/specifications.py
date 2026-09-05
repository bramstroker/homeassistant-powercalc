"""Extract editable device specification fields from ``model_schema.json``."""

from dataclasses import dataclass
from typing import Any, Literal

SpecValueType = Literal["string", "number", "integer", "boolean"]
SpecCollection = Literal["scalar", "array", "scalar_or_array"]


@dataclass(frozen=True)
class DeviceSpecField:
    """A single schema-backed ``device_specs`` form field."""

    name: str
    label: str
    description: str
    value_type: SpecValueType
    collection: SpecCollection = "scalar"
    options: tuple[str, ...] = ()


def device_spec_fields(schema: dict[str, Any]) -> dict[str, tuple[DeviceSpecField, ...]]:
    """Return the applicable device specification fields per device type."""

    device_types = _device_types(schema)
    if not device_types:
        return {}
    properties = schema.get("properties")
    base_specs = properties.get("device_specs") if isinstance(properties, dict) else None
    base_fields = _fields_from_object(base_specs, schema) if isinstance(base_specs, dict) else {}
    fields_by_type = {device_type: dict(base_fields) for device_type in device_types}

    conditions = schema.get("allOf")
    if isinstance(conditions, list):
        _apply_conditional_fields(fields_by_type, conditions, schema)
    return {device_type: tuple(fields.values()) for device_type, fields in fields_by_type.items()}


def _device_types(schema: dict[str, Any]) -> tuple[str, ...]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return ()
    device_type_schema = properties.get("device_type")
    if not isinstance(device_type_schema, dict):
        return ()
    values = device_type_schema.get("enum")
    return tuple(value for value in values if isinstance(value, str)) if isinstance(values, list) else ()


def _apply_conditional_fields(
    fields_by_type: dict[str, dict[str, DeviceSpecField]],
    conditions: list[object],
    schema: dict[str, Any],
) -> None:
    for condition in conditions:
        if not isinstance(condition, dict):
            continue
        matching_types = _condition_device_types(condition.get("if"))
        if matching_types is None:
            continue
        then_schema = condition.get("then")
        if not isinstance(then_schema, dict):
            continue
        then_properties = then_schema.get("properties")
        if not isinstance(then_properties, dict):
            continue
        specs_schema = then_properties.get("device_specs")
        if not isinstance(specs_schema, dict):
            continue
        conditional_fields = _fields_from_object(specs_schema, schema)
        for device_type in matching_types:
            if device_type in fields_by_type:
                fields_by_type[device_type].update(conditional_fields)


def _condition_device_types(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, dict):
        return None
    properties = value.get("properties")
    if not isinstance(properties, dict) or set(properties) != {"device_type"}:
        return None
    condition = properties.get("device_type")
    if not isinstance(condition, dict):
        return None
    constant = condition.get("const")
    if isinstance(constant, str):
        return (constant,)
    choices = condition.get("enum")
    if isinstance(choices, list):
        return tuple(choice for choice in choices if isinstance(choice, str))
    return None


def _fields_from_object(value: dict[str, Any], root: dict[str, Any]) -> dict[str, DeviceSpecField]:
    schema = _resolve(value, root)
    fields: dict[str, DeviceSpecField] = {}
    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for part in all_of:
            if isinstance(part, dict):
                fields.update(_fields_from_object(part, root))
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return fields
    for name, field_schema in properties.items():
        if isinstance(name, str) and isinstance(field_schema, dict):
            field = _field_from_schema(name, field_schema, root)
            if field is not None:
                fields[name] = field
    return fields


def _field_from_schema(name: str, value: dict[str, Any], root: dict[str, Any]) -> DeviceSpecField | None:
    schema = _resolve(value, root)
    collection: SpecCollection = "scalar"
    item_schema = schema
    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        resolved_options = [_resolve(option, root) for option in one_of if isinstance(option, dict)]
        scalar = next((option for option in resolved_options if option.get("type") != "array"), None)
        array = next((option for option in resolved_options if option.get("type") == "array"), None)
        if scalar is not None and array is not None:
            items = array.get("items")
            item_schema = scalar if not isinstance(items, dict) else _resolve(items, root)
            collection = "scalar_or_array"
    if schema.get("type") == "array":
        items = schema.get("items")
        if not isinstance(items, dict):
            return None
        item_schema = _resolve(items, root)
        collection = "array"

    value_type = item_schema.get("type")
    if value_type not in {"string", "number", "integer", "boolean"}:
        return None
    raw_options = item_schema.get("enum")
    options = tuple(str(option) for option in raw_options) if isinstance(raw_options, list) else ()
    description = schema.get("description")
    return DeviceSpecField(
        name=name,
        label=name.replace("_", " ").capitalize(),
        description=description if isinstance(description, str) else "",
        value_type=value_type,
        collection=collection,
        options=options,
    )


def _resolve(value: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    reference = value.get("$ref")
    if not isinstance(reference, str) or not reference.startswith("#/"):
        return value
    resolved: object = root
    for part in reference[2:].split("/"):
        if not isinstance(resolved, dict):
            return value
        resolved = resolved.get(part.replace("~1", "/").replace("~0", "~"))
    if not isinstance(resolved, dict):
        return value
    return {**resolved, **{key: item for key, item in value.items() if key != "$ref"}}
