"""Deterministic negative-control intent guard driven by operation policies."""
from __future__ import annotations

import re
import unicodedata

from app.operations.policies import load_policies

_APOSTROPHE_TRANSLATION = str.maketrans({"‘": "'", "’": "'", "＇": "'"})


def normalized_intent(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.translate(_APOSTROPHE_TRANSLATION)
    return re.sub(r"\s+", " ", normalized).strip()


def negative_control_reason(text: str, operation_id: str) -> str | None:
    policies = load_policies()
    policy = policies.get(operation_id)
    if not policy.mutates:
        return None
    normalized = normalized_intent(text)
    if any(phrase in normalized for phrase in policies.global_negative_phrases):
        return "explicit_negative_intent"
    if any(phrase in normalized for phrase in policy.negative_phrases):
        return "explicit_negative_intent"
    return None
