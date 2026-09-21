"""Derive a single confirmation-bound job request from a committed settings save."""
from __future__ import annotations

from app.language_operations.contracts import LanguageResponse
from app.operations.contracts import OperationRequest, OperationTarget


def generation_request(response: LanguageResponse) -> OperationRequest:
    """Only receipt values supply the target and revision; never model output."""
    if response.result is None or not response.generate_after_save:
        raise ValueError("a committed settings receipt is required")
    return OperationRequest(
        operation_id="project.generation.start", operation_version=1,
        arguments={"kind": "full"},
        target=OperationTarget(project_id=response.result.project_id),
        request_id=f"{response.core_request_id}-generation",
        base_revision=response.result.revision,
    )
