"""All Tools orchestration; only the existing operation core may mutate state."""
from __future__ import annotations

import asyncio
import hmac
from time import perf_counter

from sqlalchemy.orm import Session

from app.interpretation.contracts import CandidateRef, ClarificationProposal, FailureView, InterpretationInput, OperationProposal
from app.interpretation.service import Interpreter
from app.interpretation.transport import StructuredAdapter
from app.language_operations import dialogue, observability, repository
from app.language_operations.candidate_state import current_candidates
from app.language_operations.contracts import LanguageError, LanguageExecution, LanguageInput, LanguageResponse
from app.language_operations.intent_guard import negative_control_reason
from app.language_operations.references import reference_question
from app.language_operations.pronunciation import merged_arguments, reading_question
from app.language_operations.subtitle_values import subtitle_question
from app.language_operations.pending_settings import pending_settings_question
from app.language_operations.settings_values import settings_value_question
from app.operations.catalog import OperationCatalog
from app.operations.contracts import OperationRequest, OperationTarget, Readiness
from app.operations.errors import OperationError
from app.operations.service import OperationService
from app.semantic_interpretation.interface import CandidateInterpreter

_GENERATION = {"project.generation.start", "project.generation.retry"}


class LanguageOperationService:
    def __init__(
        self, core: OperationService, adapter: StructuredAdapter | None = None,
        *, review_all: bool = False, semantic: CandidateInterpreter | None = None,
        readiness_annotations: bool = False,
    ) -> None:
        self.core = core
        self.adapter = adapter
        self.review_all = review_all
        self.semantic = semantic
        self.readiness_annotations = readiness_annotations

    async def prepare(self, db: Session, request: LanguageInput) -> LanguageResponse:
        """Freeze a model proposal; this method never calls execute."""
        response, owner, state = repository.claim(db, request)
        if owner is None or state is None:
            observability.record(response, "replay_or_precheck")
            return response
        started = perf_counter()
        guard_code = None
        try:
            if request.continuation and request.continuation.relation == "dismiss":
                response = response.model_copy(update={"status": "dismissed"})
            elif self.adapter is None:
                response = response.model_copy(update={"status": "error", "failure": FailureView(
                    reason_code="model_not_configured", message="自然言語用のローカルモデルが設定されていません。")})
            else:
                definitions = tuple(self.core.list_definitions())
                catalog = OperationCatalog(definitions=definitions)
                refs = [CandidateRef(operation_id=item.operation_id, operation_version=item.operation_version) for item in definitions]
                response = response.model_copy(update={"diagnostics": response.diagnostics.model_copy(update={"candidates": refs})})
                turns = dialogue.context(db, request)
                db.rollback()
                db.expire_all()
                interpretation_input = InterpretationInput(
                    text=request.text, state=state, dialogue=turns,
                    candidates=tuple(CandidateRef(operation_id=item.operation_id,
                                                  operation_version=item.operation_version) for item in definitions),
                )
                if self.semantic is None:
                    outcome = await Interpreter(catalog, self.adapter).preview(interpretation_input)
                else:
                    provider = (lambda offered: current_candidates(db, self.core, offered, response.project_id)) if self.readiness_annotations else None
                    semantic = await self.semantic.preview(catalog, self.adapter, interpretation_input,
                                                           readiness_provider=provider)
                    outcome = semantic.interpretation
                    response = response.model_copy(update={"mode": "all_tools" if semantic.trace.policy == "all-tools-v1" else "semantic", "diagnostics":
                        response.diagnostics.model_copy(update={"retrieval": semantic.trace,
                            "candidates": list(semantic.candidates)})})
                response = response.model_copy(update={"interpretation": outcome})
                question = reference_question(dialogue.reference_text(request, turns, outcome.proposal), outcome.proposal) if isinstance(outcome.proposal, OperationProposal) else None
                guard_code = "reference" if question else None
                if question is None and isinstance(outcome.proposal, OperationProposal):
                    question = subtitle_question(request.text, turns,
                        request.continuation.relation if request.continuation else None, outcome.proposal)
                    guard_code = "subtitle_value" if question else None
                if question is None and isinstance(outcome.proposal, OperationProposal):
                    question = settings_value_question(request.text, turns,
                        request.continuation.relation if request.continuation else None, outcome.proposal)
                    guard_code = "settings_value" if question else None
                if question is None and isinstance(outcome.proposal, OperationProposal):
                    question = pending_settings_question(turns,
                        request.continuation.relation if request.continuation else None, outcome.proposal)
                    guard_code = "pending_settings" if question else None
                if question is None and isinstance(outcome.proposal, OperationProposal):
                    question = reading_question([turn.text for turn in turns] + [request.text], outcome.proposal)
                    guard_code = "reading" if question else None
                    if outcome.proposal.operation_id == "project.settings.update" and not outcome.proposal.arguments:
                        question = ClarificationProposal(kind="clarification", question="どの設定を、どの値に変更しますか？", missing_fields=["arguments"])
                        guard_code = "empty_settings"
                negative_reason = None
                if question is None and isinstance(outcome.proposal, OperationProposal):
                    negative_reason = negative_control_reason(request.text, outcome.proposal.operation_id)
                if question is not None:
                    # Retain the original structured interpretation for audit;
                    # the application asks instead of executing a guessed ID.
                    response = response.model_copy(update={"status": "needs_input", "clarification": question})
                elif negative_reason is not None:
                    guard_code = "negative_intent"
                    response = response.model_copy(update={"status": "dismissed"})
                elif not isinstance(outcome.proposal, OperationProposal):
                    clarification = outcome.proposal if isinstance(outcome.proposal, ClarificationProposal) else None
                    if clarification and clarification.question.strip().rstrip("。.!?？") == request.text.strip().rstrip("。.!?？"):
                        clarification = clarification.model_copy(update={"question": "操作する対象を選択してください。" if clarification.missing_fields == ["target"]
                            else "変更する値や読み方など、不足している内容を指定してください。"})
                    response = response.model_copy(update={"status": outcome.status, "failure": outcome.failure,
                        "clarification": clarification})
                else:
                    proposal = outcome.proposal
                    prepared = OperationRequest(
                        operation_id=proposal.operation_id, operation_version=proposal.operation_version,
                        target=OperationTarget(project_id=response.project_id), arguments=merged_arguments(db, response.project_id, proposal),
                        request_id=response.core_request_id, base_revision=response.base_revision,
                        generation_requested=False,
                    )
                    confirmation = repository.digest({"request_id": request.request_id,
                                                       "prepared_request": prepared.model_dump(mode="json")})
                    response = response.model_copy(update={
                        "status": "ready", "prepared_request": prepared,
                        "generate_after_save": proposal.generate_after_save,
                        "confirmation_token": confirmation,
                        "requires_confirmation": self.review_all or request.review_all or proposal.operation_id in _GENERATION,
                    })
                    # Expire read snapshots before asking the core about the latest state.
                    db.rollback()
                    db.expire_all()
                    readiness = self.core.readiness(db, prepared)
                    if readiness.readiness != Readiness.ready:
                        response = response.model_copy(update={"status": "blocked", "failure": FailureView(
                            reason_code=readiness.reason_code or "not_ready",
                            message="対象の状態が変わったか、この操作を現在実行できません。最新の状態を確認してください。")})
        except asyncio.CancelledError:
            response = response.model_copy(update={"status": "error", "failure": FailureView(
                reason_code="interpretation_interrupted", message="解釈処理が中断されました。設定は変更していません。")})
            repository.finish_interpretation(db, request.request_id, owner, response)
            raise
        except OperationError as exc:
            response = response.model_copy(update={"status": "blocked", "failure": FailureView(
                reason_code=exc.reason_code, message=str(exc))})
        except Exception:
            # A transport/plugin may violate the safe exception contract. Never
            # expose its exception string or raw request/response in public logs.
            response = response.model_copy(update={"status": "error", "failure": FailureView(
                reason_code="interpretation_failed", message="解釈処理に失敗しました。設定は変更していません。")})
        response = response.model_copy(update={"diagnostics": response.diagnostics.model_copy(update={
            "interpretation_ms": round((perf_counter() - started) * 1000), "guard_code": guard_code,
        })})
        response = repository.finish_interpretation(db, request.request_id, owner, response)
        observability.record(response, "prepared")
        return response

    async def submit(self, db: Session, request: LanguageInput) -> LanguageResponse:
        """Execute an unambiguous non-confirming proposal using the common core."""
        response = await self.prepare(db, request)
        if response.status != "ready" or response.requires_confirmation or response.result is not None:
            return response
        return await asyncio.to_thread(self.execute, db, request.request_id, LanguageExecution(
            confirmation_token=response.confirmation_token,
        ))

    def get(self, db: Session, request_id: str) -> LanguageResponse:
        return repository.lookup(db, request_id)

    def execute(self, db: Session, request_id: str, confirmation: LanguageExecution) -> LanguageResponse:
        response = repository.lookup(db, request_id)
        if response.result is not None and (not response.generate_after_save or response.generation_result is not None):
            return response
        if response.result is not None and response.generation_request is not None:
            save_token = repository.digest({"request_id": request_id,
                "prepared_request": response.prepared_request.model_dump(mode="json")})
            if hmac.compare_digest(confirmation.confirmation_token, save_token):
                # Replaying the save confirmation must never confirm the next phase.
                return response
        if response.status != "ready" or response.prepared_request is None or response.confirmation_token is None:
            raise LanguageError("request_not_ready", "この要求は実行できる状態ではありません。")
        if not hmac.compare_digest(confirmation.confirmation_token, response.confirmation_token):
            raise LanguageError("confirmation_mismatch", "確認内容が保存済みの提案と一致しません。")
        prepared = response.generation_request or response.prepared_request
        if prepared.operation_id in _GENERATION and not confirmation.confirm_generation:
            raise LanguageError("generation_confirmation_required", "動画生成の対象と内容を確認してから開始してください。")
        started = perf_counter()
        try:
            result = self.core.execute(db, prepared,
                                       before_dispatch=lambda session: dialogue.require_current(session, request_id))
            response = response.model_copy(update={"status": "completed",
                                                   "generation_result" if response.generation_request else "result": result,
                                                   "executed": True, "failure": None,
                                                   "requires_confirmation": False})
        except OperationError as exc:
            response = response.model_copy(update={"status": "blocked", "failure": FailureView(
                reason_code=exc.reason_code, message=str(exc))})
        response = response.model_copy(update={"diagnostics": response.diagnostics.model_copy(update={
            "generation_execution_ms" if response.generation_request else "execution_ms": round((perf_counter() - started) * 1000),
        })})
        response = repository.acknowledge(db, request_id, response)
        observability.record(response, "executed")
        return response
