"""Public job metadata, with safe retry guidance and unambiguous UTC timestamps."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import object_session

from app.models.external_call import ExternalCall
from app.models.job import GenerationJob, JobStatus
from app.schemas import JobSummary
from app.services.generation_plan import STAGE_ORDER


def utc_timestamp(value: datetime | None) -> str | None:
    """SQLite drops timezone information; persisted application clocks are UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _retry_blocked_reason(job: GenerationJob) -> str | None:
    if job.status == JobStatus.unknown:
        return "外部処理の結果が未確定です。このアプリでは結果を照会できないため、外部サービス側の履歴を確認してください。"
    if job.status not in {JobStatus.failed, JobStatus.cancelled}:
        return None
    db = object_session(job)
    if db is None:
        return "現在の状態を再取得してから再実行してください。"
    unknown_job = db.scalar(select(GenerationJob.id).where(
        GenerationJob.project_id == job.project_id,
        GenerationJob.status == JobStatus.unknown,
    ).limit(1))
    unresolved_call = db.scalar(select(ExternalCall.id).join(
        GenerationJob, GenerationJob.id == ExternalCall.job_id,
    ).where(
        GenerationJob.project_id == job.project_id,
        or_(ExternalCall.status == "unknown", and_(
            ExternalCall.status == "in_flight", ExternalCall.remote_side_effect.is_(True),
        )),
    ).limit(1))
    if unknown_job is not None or unresolved_call is not None:
        return "以前の外部処理の結果が未確定です。外部サービス側の履歴を確認できるまで再実行できません。"
    return None


def job_summary(job: GenerationJob) -> JobSummary:
    """Expose control metadata without snapshots, provider responses or secrets."""
    blocked_reason = _retry_blocked_reason(job)
    raw_stages = (job.plan_json or {}).get("stages", [])
    stages = raw_stages if isinstance(raw_stages, list) else []
    plan = {"stages": [stage for stage in STAGE_ORDER if stage in stages]} if job.plan_json else None
    return JobSummary(
        id=job.id, project_id=job.project_id, current_stage=job.current_stage,
        status=job.status.value, progress=job.progress, stage_progress=job.stage_progress,
        started_at=utc_timestamp(job.started_at), finished_at=utc_timestamp(job.finished_at),
        error_message=job.error_message, cancel_requested=job.cancel_requested,
        input_revision=job.input_revision, parent_job_id=job.parent_job_id,
        recovery_message=job.recovery_message,
        retryable=job.status in {JobStatus.failed, JobStatus.cancelled} and blocked_reason is None,
        retry_blocked_reason=blocked_reason, plan=plan,
    )
