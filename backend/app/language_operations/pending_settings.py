"""Prevent a short answer from silently dropping pending compound intent."""
from __future__ import annotations

from typing import Literal

from app.interpretation.contracts import ClarificationProposal, DialogueContextTurn, OperationProposal


def pending_settings_question(
    turns: tuple[DialogueContextTurn, ...], relation: Literal["answer", "correction", "dismiss"] | None,
    proposal: OperationProposal,
) -> ClarificationProposal | None:
    """Previous proposals can veto partial saves, but never supply executable values."""
    if relation != "answer" or proposal.operation_id not in {
        "project.settings.update", "project.subtitle-font-size.set", "project.subtitle-font-size.adjust",
    }:
        return None
    current = proposal.arguments
    if proposal.operation_id == "project.settings.update" and proposal.operation_version == 2:
        current = current["settings"]
    for turn in reversed(turns):
        if turn.settings_saved or turn.status == "completed":
            break
        prior = turn.proposal
        if not isinstance(prior, OperationProposal) or prior.operation_id != "project.settings.update":
            continue
        fields = prior.arguments["settings"] if prior.operation_version == 2 else prior.arguments
        required = set(fields) - {"subtitle_font_size"}
        present = set(current) if proposal.operation_id == "project.settings.update" else set()
        if required - present or (prior.generate_after_save and not proposal.generate_after_save):
            return ClarificationProposal(kind="clarification", missing_fields=["arguments", "intent"],
                question="前の依頼の設定や生成希望が今回の提案から抜けています。字幕サイズ・ほかの設定・生成の希望をまとめて、もう一度指定してください。まだ保存していません。")
    return None
