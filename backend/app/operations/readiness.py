"""Resolve project targets and evaluate current execution readiness."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import GenerationJob, JobStatus
from app.models.project import Project
from app.operations.contracts import (
    OperationDefinition,
    OperationTarget,
    Readiness,
    ReadinessResult,
)
from app.workers.job_runner import job_registry


def project_state_revision(project: Project) -> str:
    """Return the current observation token without claiming durable revision semantics."""
    return project.updated_at.isoformat() if project.updated_at else "uncommitted"


def resolve_project(db: Session, target: OperationTarget) -> Project | None:
    """Load the single unambiguous target project."""
    project_id = target.resolved_id
    return db.get(Project, project_id) if project_id is not None else None


def has_live_job(db: Session, project_id: int) -> bool:
    """Return whether a pending/running row also has a live process task."""
    job_ids = db.scalars(
        select(GenerationJob.id).where(
            GenerationJob.project_id == project_id,
            GenerationJob.status.in_([JobStatus.pending, JobStatus.running]),
        )
    )
    return any(job_registry.is_running(job_id) for job_id in job_ids)


def evaluate_readiness(
    db: Session,
    definition: OperationDefinition,
    target: OperationTarget,
) -> ReadinessResult:
    """Evaluate target existence and live-state constraints for an operation."""
    project_id = target.resolved_id
    if project_id is None:
        return ReadinessResult(
            operation_id=definition.operation_id,
            readiness=Readiness.needs_input,
            reason_code="target_required",
            missing_fields=["project_id"],
        )
    project = resolve_project(db, target)
    if project is None:
        return ReadinessResult(
            operation_id=definition.operation_id,
            readiness=Readiness.unsupported,
            reason_code="target_not_found",
            project_id=project_id,
        )
    if definition.precondition_key == "project_editable" and has_live_job(db, project_id):
        return ReadinessResult(
            operation_id=definition.operation_id,
            readiness=Readiness.blocked,
            reason_code="project_busy",
            project_id=project_id,
            state_revision=project_state_revision(project),
        )
    return ReadinessResult(
        operation_id=definition.operation_id,
        readiness=Readiness.ready,
        project_id=project_id,
        state_revision=project_state_revision(project),
    )
