"""Deterministic negative-control intent guard."""
from __future__ import annotations

import re
import unicodedata

_APOSTROPHE_TRANSLATION = str.maketrans({"\u2018": "'", "\u2019": "'", "\uff07": "'"})

MUTATING_OPERATIONS: frozenset[str] = frozenset({
    "project.subtitle-font-size.adjust",
    "project.subtitle-font-size.set",
    "project.settings.update",
    "project.generation.start",
    "project.generation.cancel",
    "project.generation.retry",
    "project.settings.restore",
})
RETRY_OPERATIONS: frozenset[str] = frozenset({"project.generation.retry"})
CANCELLATION_OPERATIONS: frozenset[str] = frozenset({"project.generation.cancel"})
GENERATION_OPERATIONS: frozenset[str] = frozenset({"project.generation.start"})

GLOBAL_NEGATIVE_PHRASES: frozenset[str] = frozenset({
    "何もしない",
    "実行しない",
    "変更しない",
    "do nothing",
    "do not execute",
    "don't execute",
})
RETRY_NEGATIVE_PHRASES: frozenset[str] = frozenset({
    "再試行しない",
    "再実行しない",
    "やり直さない",
    "do not retry",
    "don't retry",
})
CANCELLATION_NEGATIVE_PHRASES: frozenset[str] = frozenset({
    "キャンセルしない",
    "取り消さない",
    "停止しない",
    "do not cancel",
    "don't cancel",
})
GENERATION_NEGATIVE_PHRASES: frozenset[str] = frozenset({
    "生成しない",
    "開始しない",
    "作り直さない",
    "do not generate",
    "don't generate",
})


def normalized_intent(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.translate(_APOSTROPHE_TRANSLATION)
    return re.sub(r"\s+", " ", normalized).strip()


def negative_control_reason(text: str, operation_id: str) -> str | None:
    if operation_id not in MUTATING_OPERATIONS:
        return None

    normalized = normalized_intent(text)
    if any(phrase in normalized for phrase in GLOBAL_NEGATIVE_PHRASES):
        return "explicit_negative_intent"
    if operation_id in RETRY_OPERATIONS and any(phrase in normalized for phrase in RETRY_NEGATIVE_PHRASES):
        return "explicit_negative_intent"
    if operation_id in CANCELLATION_OPERATIONS and any(phrase in normalized for phrase in CANCELLATION_NEGATIVE_PHRASES):
        return "explicit_negative_intent"
    if operation_id in GENERATION_OPERATIONS and any(phrase in normalized for phrase in GENERATION_NEGATIVE_PHRASES):
        return "explicit_negative_intent"
    return None
