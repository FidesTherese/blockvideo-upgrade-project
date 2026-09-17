"""Validated operation orchestration shared by every structured entry point."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.operations.catalog import CatalogError, OperationCatalog, validate_arguments
from app.operations.contracts import (
    OperationDefinition,
    OperationRequest,
    OperationResult,
    Readiness,
    ReadinessResult,
)
from app.operations.readiness import evaluate_readiness, resolve_project
from app.operations.registry import HandlerRegistry, RegistryError


class OperationError(ValueError):
    """Bounded operation rejection with a machine-readable reason."""

    def __init__(
        self,
        reason_code: str,
        message: str,
        *,
        readiness: Readiness | None = None,
        result: ReadinessResult | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.readiness = readiness
        self.result = result


class OperationService:
    """Own operation lookup, validation, final readiness, and dispatch order."""

    def __init__(self, catalog: OperationCatalog, registry: HandlerRegistry) -> None:
        self._catalog = catalog.model_copy(deep=True)
        self._registry = registry
        definition_keys = {item.handler_key for item in self._catalog.definitions}
        for key in definition_keys:
            registry.require(key)
        unreferenced = registry.keys() - definition_keys
        if unreferenced:
            raise RegistryError(f"registered handlers are not defined: {sorted(unreferenced)}")

    def list_definitions(self) -> list[OperationDefinition]:
        """Return detached catalog definitions in stable operation-ID order."""
        return [item.model_copy(deep=True) for item in self._catalog.definitions]

    def _definition_and_arguments(
        self, request: OperationRequest
    ) -> tuple[OperationDefinition, dict[str, Any]]:
        try:
            definition = self._catalog.require(
                request.operation_id, request.operation_version
            )
        except CatalogError as exc:
            raise OperationError("operation_not_found", str(exc)) from exc
        try:
            arguments = validate_arguments(definition, request.arguments)
        except CatalogError as exc:
            raise OperationError("invalid_arguments", str(exc)) from exc
        return definition, arguments

    def readiness(self, db: Session, request: OperationRequest) -> ReadinessResult:
        """Validate arguments and report current target readiness."""
        definition, _arguments = self._definition_and_arguments(request)
        result = evaluate_readiness(db, definition, request.target)
        if (
            result.readiness == Readiness.ready
            and request.observed_state_revision is not None
            and request.observed_state_revision != result.state_revision
        ):
            return result.model_copy(
                update={"readiness": Readiness.blocked, "reason_code": "stale_state"}
            )
        return result

    def _require_ready(
        self, result: ReadinessResult, observed_state_revision: str | None
    ) -> None:
        if (
            result.readiness == Readiness.ready
            and observed_state_revision is not None
            and observed_state_revision != result.state_revision
        ):
            result = result.model_copy(
                update={"readiness": Readiness.blocked, "reason_code": "stale_state"}
            )
        if result.readiness != Readiness.ready:
            raise OperationError(
                result.reason_code or "not_ready",
                f"operation is not ready: {result.readiness.value}",
                readiness=result.readiness,
                result=result,
            )

    def execute(self, db: Session, request: OperationRequest) -> OperationResult:
        """Repeat final validation immediately before registered dispatch."""
        definition, arguments = self._definition_and_arguments(request)
        initial = evaluate_readiness(db, definition, request.target)
        self._require_ready(initial, request.observed_state_revision)
        project = resolve_project(db, request.target)
        if project is None:  # Defensive: readiness already resolved it.
            raise OperationError("target_not_found", "project target disappeared")
        final = evaluate_readiness(db, definition, request.target)
        self._require_ready(final, request.observed_state_revision)
        handler = self._registry.require(definition.handler_key)
        return handler(db, project, arguments)
