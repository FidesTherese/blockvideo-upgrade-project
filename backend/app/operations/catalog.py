"""Load and validate the Git-managed operation definition catalog."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from app.operations.contracts import OperationDefinition


class CatalogError(ValueError):
    """Raised for malformed definitions, schemas, or arguments."""


class OperationCatalog(BaseModel):
    """Validated collection indexed by operation ID and version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    definitions: tuple[OperationDefinition, ...]

    def require(self, operation_id: str, operation_version: int) -> OperationDefinition:
        """Return an exact operation version or raise a bounded error."""
        for definition in self.definitions:
            if (
                definition.operation_id == operation_id
                and definition.operation_version == operation_version
            ):
                return definition
        raise CatalogError(f"unknown operation: {operation_id} version {operation_version}")


_ROOT_SCHEMA_KEYS = {"type", "properties", "required", "additionalProperties"}
_PROPERTY_SCHEMA_KEYS = {"type", "minimum", "maximum", "minLength", "maxLength"}
_SUPPORTED_TYPES = {"integer", "string", "boolean"}
_KNOWN_PRECONDITIONS = {"project_exists", "project_editable"}
_KNOWN_POSTCONDITIONS = {"state_unchanged", "subtitle_font_size_saved"}
_KNOWN_ARTIFACTS = {"video"}


def _validate_input_schema(schema: dict[str, Any]) -> None:
    unknown_root = set(schema) - _ROOT_SCHEMA_KEYS
    if unknown_root:
        raise CatalogError(f"unsupported input schema keys: {sorted(unknown_root)}")
    if schema.get("type") != "object":
        raise CatalogError("input schema root type must be object")
    if schema.get("additionalProperties") is not False:
        raise CatalogError("input schema must reject additionalProperties")
    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, dict) or not isinstance(required, list):
        raise CatalogError("input schema requires properties object and required list")
    if not all(isinstance(name, str) for name in required):
        raise CatalogError("required fields must be strings")
    if not set(required) <= set(properties):
        raise CatalogError("required fields must exist in properties")
    for name, rule in properties.items():
        if not isinstance(name, str) or not isinstance(rule, dict):
            raise CatalogError("property names and schemas must be objects")
        unknown = set(rule) - _PROPERTY_SCHEMA_KEYS
        if unknown:
            raise CatalogError(f"unsupported schema keys for {name}: {sorted(unknown)}")
        property_type = rule.get("type")
        if property_type not in _SUPPORTED_TYPES:
            raise CatalogError(f"unsupported type for {name}: {property_type}")
        numeric_keys = {"minimum", "maximum"}
        length_keys = {"minLength", "maxLength"}
        if property_type == "integer":
            if set(rule) & length_keys:
                raise CatalogError(f"length constraint is invalid for integer {name}")
            values = [rule[key] for key in numeric_keys if key in rule]
            if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
                raise CatalogError(f"integer constraints for {name} must be integers")
            if "minimum" in rule and "maximum" in rule and rule["minimum"] > rule["maximum"]:
                raise CatalogError(f"minimum exceeds maximum for {name}")
        elif property_type == "string":
            if set(rule) & numeric_keys:
                raise CatalogError(f"numeric constraint is invalid for string {name}")
            values = [rule[key] for key in length_keys if key in rule]
            if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values):
                raise CatalogError(f"length constraints for {name} must be non-negative integers")
            if "minLength" in rule and "maxLength" in rule and rule["minLength"] > rule["maxLength"]:
                raise CatalogError(f"minLength exceeds maxLength for {name}")
        elif set(rule) - {"type"}:
            raise CatalogError(f"constraints are invalid for boolean {name}")


def load_catalog(path: Path) -> OperationCatalog:
    """Read a UTF-8 JSON catalog and reject ambiguous definitions."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        operations = raw["operations"]
        if set(raw) != {"operations"} or not isinstance(operations, list):
            raise CatalogError("catalog root must contain only an operations list")
        definitions = [OperationDefinition.model_validate(item) for item in operations]
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValidationError) as exc:
        raise CatalogError(f"invalid operation catalog: {exc}") from exc
    seen: set[tuple[str, int]] = set()
    for definition in definitions:
        key = (definition.operation_id, definition.operation_version)
        if key in seen:
            raise CatalogError(f"duplicate operation definition: {key}")
        seen.add(key)
        if definition.schema_version != 1:
            raise CatalogError(f"unsupported schema_version: {definition.schema_version}")
        _validate_input_schema(definition.input_schema)
        if any(not example.strip() for example in definition.examples):
            raise CatalogError("examples must contain non-empty strings")
        if definition.precondition_key not in _KNOWN_PRECONDITIONS:
            raise CatalogError(f"unknown precondition: {definition.precondition_key}")
        if definition.postcondition_key not in _KNOWN_POSTCONDITIONS:
            raise CatalogError(f"unknown postcondition: {definition.postcondition_key}")
        unknown_artifacts = set(definition.affected_artifacts) - _KNOWN_ARTIFACTS
        if unknown_artifacts:
            raise CatalogError(f"unknown affected artifacts: {sorted(unknown_artifacts)}")
    return OperationCatalog(
        definitions=tuple(sorted(definitions, key=lambda item: item.operation_id))
    )


def validate_arguments(
    definition: OperationDefinition, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Validate the catalog's strict JSON-schema subset without coercion."""
    schema = definition.input_schema
    properties: dict[str, dict[str, Any]] = schema["properties"]
    required: list[str] = schema["required"]
    missing = [name for name in required if name not in arguments]
    if missing:
        raise CatalogError(f"missing required arguments: {missing}")
    extra = set(arguments) - set(properties)
    if extra:
        raise CatalogError(f"unexpected arguments: {sorted(extra)}")
    for name, value in arguments.items():
        rule = properties[name]
        expected = rule["type"]
        valid_type = (
            (expected == "integer" and isinstance(value, int) and not isinstance(value, bool))
            or (expected == "string" and isinstance(value, str))
            or (expected == "boolean" and isinstance(value, bool))
        )
        if not valid_type:
            raise CatalogError(f"argument {name} must be {expected}")
        if expected == "integer":
            if "minimum" in rule and value < rule["minimum"]:
                raise CatalogError(f"argument {name} is below minimum")
            if "maximum" in rule and value > rule["maximum"]:
                raise CatalogError(f"argument {name} is above maximum")
        if expected == "string":
            if "minLength" in rule and len(value) < rule["minLength"]:
                raise CatalogError(f"argument {name} is too short")
            if "maxLength" in rule and len(value) > rule["maxLength"]:
                raise CatalogError(f"argument {name} is too long")
    return dict(arguments)
