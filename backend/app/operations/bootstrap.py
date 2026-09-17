"""Construct the immutable process-wide operation service."""
from __future__ import annotations

from pathlib import Path

from app.operations.catalog import load_catalog
from app.operations.handlers import get_project_status, set_subtitle_font_size
from app.operations.registry import HandlerRegistry, RegistryError
from app.operations.service import OperationService

_DEFAULT_CATALOG = Path(__file__).with_name("definitions.json")
_HANDLER_POLICIES = {
    "project.get_status": (
        "project.status.get",
        1,
        "project_exists",
        "state_unchanged",
        frozenset(),
    ),
    "project.set_subtitle_font_size": (
        "project.subtitle-font-size.set",
        1,
        "project_editable",
        "subtitle_font_size_saved",
        frozenset({"video"}),
    ),
}


def build_operation_service(catalog_path: Path = _DEFAULT_CATALOG) -> OperationService:
    """Build and cross-check catalog metadata against handler safety policy."""
    registry = HandlerRegistry()
    registry.register("project.get_status", get_project_status)
    registry.register("project.set_subtitle_font_size", set_subtitle_font_size)
    catalog = load_catalog(catalog_path)
    for definition in catalog.definitions:
        registry.require(definition.handler_key)
        actual = (
            definition.operation_id,
            definition.operation_version,
            definition.precondition_key,
            definition.postcondition_key,
            frozenset(definition.affected_artifacts),
        )
        expected = _HANDLER_POLICIES[definition.handler_key]
        if actual != expected:
            raise RegistryError(
                f"definition violates handler policy: {definition.handler_key}"
            )
    return OperationService(catalog, registry)


operation_service = build_operation_service()
