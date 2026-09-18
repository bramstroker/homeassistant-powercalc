"""Format entity references and condition values for plots and diagrams."""


def format_entity_label(entity_id: object) -> str | None:
    """Resolve a condition's first entity or portable reference to a readable label."""
    if isinstance(entity_id, list):
        entity_id = entity_id[0] if entity_id else None
    if not isinstance(entity_id, str):
        return None
    if entity_id == "[[entity]]":
        return "state"
    if entity_id.startswith("[[") and entity_id.endswith("]]"):
        entity_id = entity_id[2:-2]
    _, separator, value = entity_id.partition(":")
    return (value if separator else entity_id).replace("_", " ")


def format_value_label(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)
