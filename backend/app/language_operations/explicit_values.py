"""Tell a guessed (missing) value from one that contradicts what the user wrote.

Unattended (YOLO) requests may guess values the request leaves out, but never
override or drop a number or reference the user stated. Normal requests use the
same check as a clarifying guard. This module only reports a conflict; it never
fills or converts arguments.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.interpretation.contracts import OperationProposal
from app.operations.policies import OperationPolicies, load_policies, settings_base, settings_values

_PX = r"(?<![\d.])([0-9]+)\s*(?:px|ピクセル)(?![a-z])"
_NUMBER = r"(?<![\d.])[-+]?\d+(?:\.\d+)?(?![\d.])"
_UP = r"大き|上げ|増や|拡大"
_DOWN = r"小さ|下げ|減ら|縮小"
_CLAUSE_END = r"[、。,!！?？\n]"
_NEGATION = r"ないで|なくて|しない|ません"
# "動画3ではなく動画4に" names 3 only to exclude it.
_EXCLUDED = r"\d+\s*(?:番)?\s*(?:では|じゃ)なく(?:て)?"


def _normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _reference_conflict(text: str, proposal: OperationProposal, policies: OperationPolicies) -> bool:
    binding = policies.get(proposal.operation_id).reference
    if binding is None:
        return False
    kind = policies.references[binding.kind]
    chosen = re.sub(_EXCLUDED, " ", text)
    stated = {int(value) for pattern in kind.patterns for value in re.findall(pattern, chosen, re.IGNORECASE)}
    return bool(stated) and stated != {proposal.arguments.get(binding.argument)}


def _subtitle_conflict(text: str, values: dict[str, Any], require_all: bool) -> bool:
    pixels = {int(value) for value in re.findall(_PX, text)}
    # "64pxに" / "64pxで" names the size itself, even next to "大きく".
    targets = {int(value) for value in re.findall(_PX + r"\s*(?:に|へ|で)", text)}
    absolute, delta = values.get("subtitle_font_size"), values.get("subtitle_font_size_delta")
    up, down = bool(re.search(_UP, text)), bool(re.search(_DOWN, text))
    if require_all and pixels and absolute is None and delta is None:
        return True
    if absolute is not None and ((targets and absolute not in targets)
                                 or (pixels and absolute not in pixels and not (up or down))):
        return True
    if delta is not None:
        if (delta > 0 and down and not up) or (delta < 0 and up and not down):
            return True
        if pixels and (abs(delta) not in pixels or not (up or down) or bool(targets)):
            return True
    return False


def _stated_settings(text: str, policies: OperationPolicies) -> dict[str, tuple[float, bool]]:
    """Each setting keyword takes the first number after it, within its clause.

    The flag tells a negated statement ("話速を1.2倍にしないで") from a request.
    """
    plain = re.sub(_PX, " ", text)
    hits: list[tuple[int, int, str, str | None]] = []
    for name, patterns in policies.setting_keywords.items():
        for pattern in patterns:
            for match in re.finditer(pattern, plain):
                hits.append((match.start(), match.end(), name, match.group(1) if match.groups() else None))
    hits.sort()
    stated: dict[str, tuple[float, bool]] = {}
    for index, (start, end, name, captured) in enumerate(hits):
        negated = bool(re.search(_NEGATION, re.split(_CLAUSE_END, plain[start:], maxsplit=1)[0]))
        if captured is not None:
            stated.setdefault(name, (float(captured), negated))
            continue
        limit = hits[index + 1][0] if index + 1 < len(hits) else len(plain)
        window = re.split(_CLAUSE_END, plain[end:limit], maxsplit=1)[0]
        number = re.search(_NUMBER, window)
        if number is not None:
            stated.setdefault(name, (float(number.group()), negated))
    return stated


def _settings_conflict(text: str, proposal: OperationProposal, policies: OperationPolicies,
                       require_all: bool) -> bool:
    view = policies.settings_view(proposal.operation_id, proposal.operation_version)
    if view is None:
        return False
    if _subtitle_conflict(text, settings_values(view, proposal.arguments), require_all):
        return True
    proposed = settings_base(view, proposal.arguments) or {}
    for name, (value, negated) in _stated_settings(text, policies).items():
        current = proposed.get(name)
        matches = type(current) in {int, float} and float(current) == value
        if negated:
            if matches:
                return True  # sets exactly what the user said not to
        elif (current is None and require_all) or (current is not None and not matches):
            return True  # a stated value that is dropped or changed is never a guess
    return False


def explicit_conflict(texts: list[str], proposal: OperationProposal, *, require_all: bool = True) -> bool:
    """True when the proposal contradicts (or, for a whole request, drops) a stated value or reference."""
    policies = load_policies()
    text = _normalized("\n".join(texts))
    return (_reference_conflict(text, proposal, policies)
            or _settings_conflict(text, proposal, policies, require_all))
