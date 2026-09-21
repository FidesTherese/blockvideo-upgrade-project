"""Require explicit opaque job/history references before proposing execution."""
from __future__ import annotations

import re
import unicodedata

from app.interpretation.contracts import ClarificationProposal, OperationProposal

_JOB = re.compile(r"(?:ジョブ|job)(?:[_\s]*id)?\s*[:=#]?\s*(\d+)", re.IGNORECASE)
_REVISION = re.compile(r"(?:revision|リビジョン|設定(?:の)?(?:版|バージョン))\s*[:=#]?\s*(\d+)", re.IGNORECASE)
_NUMBERED_VERSION = re.compile(r"(?:第)?(\d+)\s*版")


def reference_question(text: str, proposal: OperationProposal) -> ClarificationProposal | None:
    """Minimal state is not a source of job IDs or a chosen historical version.

    This is a conservative reference binding, not a replacement language parser.
    Names, implicit 'previous' and multi-reference corrections need later dialogue.
    """
    text = unicodedata.normalize("NFKC", text)
    if proposal.operation_id in {"project.generation.cancel", "project.generation.retry"}:
        references = {int(value) for value in _JOB.findall(text)}
        requested = proposal.arguments["job_id"]
        question = "対象のジョブ番号を「ジョブ7」のように1つ指定してください。"
    elif proposal.operation_id == "project.settings.restore":
        references = {int(value) for pattern in (_REVISION, _NUMBERED_VERSION) for value in pattern.findall(text)}
        requested = proposal.arguments["revision"]
        question = "戻したい設定の版番号を「revision 2」のように1つ指定してください。"
    else:
        return None
    if references == {requested}:
        return None
    return ClarificationProposal(kind="clarification", question=question, missing_fields=["arguments"])
