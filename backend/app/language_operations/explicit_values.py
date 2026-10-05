"""Tell a guessed (missing) value from one that contradicts what the user wrote.

Unattended (YOLO) requests may guess values the request leaves out, but never
override a number or reference the user stated. This module only reports a
conflict; it never fills or converts arguments.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.interpretation.contracts import OperationProposal
from app.operations.policies import load_policies, settings_base, settings_values

_PX = r"(?<![\d.])([0-9]+)\s*(?:px|ピクセル)(?![a-z])"
_NUMBER = r"(?<![\d.])[-+]?\d+(?:\.\d+)?(?![\d.])"


def _normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _reference_conflict(text: str, proposal: OperationProposal) -> bool:
    policies = load_policies()
    binding = policies.get(proposal.operation_id).reference
    if binding is None:
        return False
    kind = policies.references[binding.kind]
    stated = {int(value) for pattern in kind.patterns
              for value in re.findall(pattern, _normalized(text), re.IGNORECASE)}
    return bool(stated) and stated != {proposal.arguments.get(binding.argument)}


def _settings_conflict(text: str, proposal: OperationProposal) -> bool:
    view = load_policies().settings_view(proposal.operation_id, proposal.operation_version)
    if view is None:
        return False
    normalized = _normalized(text)
    pixels = {int(value) for value in re.findall(_PX, normalized)}
    values: dict[str, Any] = settings_values(view, proposal.arguments)
    absolute, delta = values.get("subtitle_font_size"), values.get("subtitle_font_size_delta")
    if pixels and ((absolute is not None and absolute not in pixels)
                   or (delta is not None and abs(delta) not in pixels)):
        return True
    # Numbers other than pixel sizes belong to other settings (speed, speaker, ...).
    numbers = {float(value) for value in re.findall(_NUMBER, re.sub(_PX, " ", normalized))}
    others = {key: value for key, value in (settings_base(view, proposal.arguments) or {}).items()
              if key != "subtitle_font_size" and type(value) in {int, float}}
    return bool(numbers) and any(float(value) not in numbers for value in others.values())


def explicit_conflict(texts: list[str], proposal: OperationProposal) -> bool:
    """True when the proposal contradicts a reference or number the user wrote."""
    text = "\n".join(texts)
    return _reference_conflict(text, proposal) or _settings_conflict(text, proposal)
