"""Bind supplied readings and merge language additions without losing saved entries."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy.orm import Session

from app.interpretation.contracts import ClarificationProposal, OperationProposal
from app.models.project import Project


def normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return "".join(chr(ord(char) + 0x60) if "ぁ" <= char <= "ゖ" else char for char in text)


def reading_question(texts: list[str], proposal: OperationProposal) -> ClarificationProposal | None:
    if proposal.operation_id != "project.settings.update":
        return None
    supplied = normalized("\n".join(texts))
    settings = proposal.arguments["settings"] if proposal.operation_version == 2 else proposal.arguments
    for item in settings.get("pronunciation_overrides", []):
        surface, reading = item["surface"], item["reading"]
        if normalized(surface) not in supplied or normalized(reading) not in supplied:
            return ClarificationProposal(kind="clarification", question="登録する表記と読み方を教えてください。質問に表記がある場合は読み方だけで構いません。", missing_fields=["arguments"])
        accent = item.get("accent")
        if accent is not None and not re.search(rf"アクセント\s*(?:は|を)?\s*[:：]?\s*{accent}(?!\d)", supplied):
            return ClarificationProposal(kind="clarification", question="アクセントの値を指定するか、自動と指定してください。", missing_fields=["arguments"])
    return None


def merged_arguments(db: Session, project_id: int, proposal: OperationProposal) -> dict[str, Any]:
    arguments = dict(proposal.arguments)
    nested = proposal.operation_id == "project.settings.update" and proposal.operation_version == 2
    settings = dict(arguments["settings"]) if nested else arguments
    additions = settings.get("pronunciation_overrides") if proposal.operation_id == "project.settings.update" else None
    if additions:
        project = db.get(Project, project_id)
        existing = project.pronunciation_overrides if project else []
        by_surface = {item["surface"]: dict(item) for item in existing or []}
        by_surface.update({item["surface"]: dict(item) for item in additions})
        settings["pronunciation_overrides"] = list(by_surface.values())
    if nested:
        arguments["settings"] = settings
    return arguments
