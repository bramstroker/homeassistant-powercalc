from typing import Any

import pytest
import voluptuous as vol

from custom_components.powercalc.flow_helper.common import (
    fill_schema_defaults,
    unwrap_choose_selector,
    wrap_choose_selector,
)


@pytest.mark.parametrize(
    "user_input,wrapper_key,value_key,expected",
    [
        # wrapper_key not present -> returned unchanged
        (
            {"foo": 1},
            "missing",
            None,
            {"foo": 1},
        ),
        # raw is scalar, no value_key -> wrapper dropped, no remap
        (
            {"foo": 1, "wrap": 42},
            "wrap",
            None,
            {"foo": 1},
        ),
        # raw is scalar with string value_key -> stored under that key
        (
            {"wrap": 42},
            "wrap",
            "remapped",
            {"remapped": 42},
        ),
        # raw is scalar with callable value_key -> stored under returned key
        (
            {"wrap": 42},
            "wrap",
            lambda value: f"key_{value}",
            {"key_42": 42},
        ),
        # raw is dict without "active_choice" -> merged flatly into user_input
        (
            {"wrap": {"a": 1, "b": 2}},
            "wrap",
            None,
            {"a": 1, "b": 2},
        ),
        # active_choice with None value -> wrapper dropped, nothing added
        (
            {"wrap": {"active_choice": "power", "power": None}},
            "wrap",
            None,
            {},
        ),
        # active_choice with scalar value -> stored under the active choice key
        (
            {"wrap": {"active_choice": "power", "power": 100}},
            "wrap",
            None,
            {"power": 100},
        ),
        # active_choice with dict value -> merged flatly into user_input
        (
            {"wrap": {"active_choice": "states_power", "states_power": {"state_a": 10, "state_b": 20}}},
            "wrap",
            None,
            {"state_a": 10, "state_b": 20},
        ),
        # active_choice missing in raw mapping -> referenced key is absent so value is None, wrapper dropped
        (
            {"wrap": {"active_choice": "power"}},
            "wrap",
            None,
            {},
        ),
        # other keys in user_input are preserved
        (
            {"foo": "bar", "wrap": {"active_choice": "power", "power": 5}},
            "wrap",
            None,
            {"foo": "bar", "power": 5},
        ),
    ],
)
def test_unwrap_choose_selector(
    user_input: dict[str, Any],
    wrapper_key: str,
    value_key: str | None,
    expected: dict[str, Any],
) -> None:
    result = unwrap_choose_selector(user_input, wrapper_key, value_key)
    assert result == expected


def test_unwrap_choose_selector_mutates_input() -> None:
    """The helper mutates and returns the same dict, callers rely on this."""
    user_input = {"wrap": {"active_choice": "power", "power": 100}}
    result = unwrap_choose_selector(user_input, "wrap")
    assert result is user_input


@pytest.mark.parametrize(
    "form_data,wrapper_key,choices,raw_value,expected",
    [
        # No matching keys in form_data -> form_data returned unchanged
        (
            {"foo": 1},
            "wrap",
            {"power": "power", "states_power": "states_power"},
            False,
            {"foo": 1},
        ),
        # String mapping match -> wrapped as ChooseSelector dict
        (
            {"power": 100},
            "wrap",
            {"power": "power"},
            False,
            {"power": 100, "wrap": {"active_choice": "power", "power": 100}},
        ),
        # List mapping match -> choice value is a dict of the matching keys
        (
            {"min_power": 5, "max_power": 50},
            "wrap",
            {"linear": ["min_power", "max_power"]},
            False,
            {
                "min_power": 5,
                "max_power": 50,
                "wrap": {"active_choice": "linear", "linear": {"min_power": 5, "max_power": 50}},
            },
        ),
        # List mapping with only some keys present -> choice value contains only present keys
        (
            {"min_power": 5},
            "wrap",
            {"linear": ["min_power", "max_power"]},
            False,
            {
                "min_power": 5,
                "wrap": {"active_choice": "linear", "linear": {"min_power": 5}},
            },
        ),
        # raw_value=True with string mapping -> wrapper holds the raw value, no active_choice envelope
        (
            {"power": 100},
            "wrap",
            {"power": "power"},
            True,
            {"power": 100, "wrap": 100},
        ),
        # raw_value=True with list mapping -> wrapper holds the dict, no active_choice envelope
        (
            {"min_power": 5, "max_power": 50},
            "wrap",
            {"linear": ["min_power", "max_power"]},
            True,
            {"min_power": 5, "max_power": 50, "wrap": {"min_power": 5, "max_power": 50}},
        ),
        # First matching choice wins, later choices are skipped even when present
        (
            {"power": 100, "states_power": [{"state": "on", "power": 5}]},
            "wrap",
            {"power": "power", "states_power": "states_power"},
            False,
            {
                "power": 100,
                "states_power": [{"state": "on", "power": 5}],
                "wrap": {"active_choice": "power", "power": 100},
            },
        ),
        # Choices iterated in order, first one without matches is skipped to find the second
        (
            {"states_power": [{"state": "on", "power": 5}]},
            "wrap",
            {"power": "power", "states_power": "states_power"},
            False,
            {
                "states_power": [{"state": "on", "power": 5}],
                "wrap": {"active_choice": "states_power", "states_power": [{"state": "on", "power": 5}]},
            },
        ),
    ],
)
def test_wrap_choose_selector(
    form_data: dict[str, Any],
    wrapper_key: str,
    choices: dict[str, list[str] | str],
    raw_value: bool,
    expected: dict[str, Any],
) -> None:
    result = wrap_choose_selector(form_data, wrapper_key, choices, raw_value=raw_value)
    assert result == expected


def test_wrap_choose_selector_returns_new_dict_on_match() -> None:
    """A match returns a fresh dict rather than mutating form_data."""
    form_data = {"power": 100}
    result = wrap_choose_selector(form_data, "wrap", {"power": "power"})
    assert result is not form_data
    assert "wrap" not in form_data


def test_wrap_choose_selector_returns_same_dict_on_no_match() -> None:
    """When no choices match, the original dict is returned as-is."""
    form_data = {"foo": "bar"}
    result = wrap_choose_selector(form_data, "wrap", {"power": "power"})
    assert result is form_data


def _find_marker(schema: vol.Schema, name: str) -> vol.Marker:
    return next(key for key in schema.schema if getattr(key, "schema", key) == name)


def test_fill_schema_defaults_key_not_in_options() -> None:
    """A marker whose schema name is missing from options is left untouched."""
    original = vol.Required("foo")
    schema = vol.Schema({original: str})

    result = fill_schema_defaults(schema, {"other": "value"})

    new_key = _find_marker(result, "foo")
    assert new_key is original


def test_fill_schema_defaults_plain_string_key_left_untouched() -> None:
    """Non-Marker keys (raw strings) are passed through unchanged."""
    schema = vol.Schema({"foo": str})

    result = fill_schema_defaults(schema, {"foo": "bar"})

    assert "foo" in result.schema
    assert result.schema["foo"] is str


def test_fill_schema_defaults_optional_with_truthy_default_is_replaced() -> None:
    """vol.Optional with a callable default returning truthy gets a new default from options."""
    schema = vol.Schema({vol.Optional("foo", default="old"): str})

    result = fill_schema_defaults(schema, {"foo": "new"})

    new_key = _find_marker(result, "foo")
    assert isinstance(new_key, vol.Optional)
    assert new_key.default() == "new"


def test_fill_schema_defaults_required_gets_default_and_suggested_value() -> None:
    """vol.Required gets both a new default and a suggested_value description."""
    schema = vol.Schema({vol.Required("foo"): str})

    result = fill_schema_defaults(schema, {"foo": "bar"})

    new_key = _find_marker(result, "foo")
    assert isinstance(new_key, vol.Required)
    assert new_key.default() == "bar"
    assert new_key.description == {"suggested_value": "bar"}


def test_fill_schema_defaults_required_with_existing_default_is_overwritten() -> None:
    """vol.Required with an existing default is still replaced (Required branch wins)."""
    schema = vol.Schema({vol.Required("foo", default="old"): str})

    result = fill_schema_defaults(schema, {"foo": "new"})

    new_key = _find_marker(result, "foo")
    assert isinstance(new_key, vol.Required)
    assert new_key.default() == "new"
    assert new_key.description == {"suggested_value": "new"}


def test_fill_schema_defaults_optional_no_default_gets_suggested_value() -> None:
    """vol.Optional without a default gets a copied marker with a suggested_value description."""
    original = vol.Optional("foo")
    schema = vol.Schema({original: str})

    result = fill_schema_defaults(schema, {"foo": "baz"})

    new_key = _find_marker(result, "foo")
    assert new_key is not original
    assert new_key.description == {"suggested_value": "baz"}


def test_fill_schema_defaults_optional_with_falsy_default_gets_suggested_value() -> None:
    """vol.Optional whose default() is falsy falls through to the suggested_value branch."""
    schema = vol.Schema({vol.Optional("foo", default=False): bool})

    result = fill_schema_defaults(schema, {"foo": True})

    new_key = _find_marker(result, "foo")
    assert isinstance(new_key, vol.Optional)
    assert new_key.default() is False
    assert new_key.description == {"suggested_value": True}


def test_fill_schema_defaults_optional_with_existing_suggested_value_left_untouched() -> None:
    """An Optional that already exposes a suggested_value description is not modified."""
    original = vol.Optional("foo", description={"suggested_value": "existing"})
    schema = vol.Schema({original: str})

    result = fill_schema_defaults(schema, {"foo": "ignored"})

    new_key = _find_marker(result, "foo")
    assert new_key is original
    assert new_key.description == {"suggested_value": "existing"}
