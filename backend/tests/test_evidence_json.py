from __future__ import annotations

import importlib
import json
from typing import Any, Literal

import pytest
from pydantic import BaseModel, ConfigDict

from evaluation.tool_attestation import canonical_json_bytes


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    values: tuple[str | int | float, ...]


def _parse(raw: bytes, maximum: int = 100_000) -> Evidence:
    parser = importlib.import_module("evaluation.evidence_json")
    return parser.parse_canonical_model(raw, Evidence, maximum=maximum)


def test_canonical_json_preserves_exact_ascii_lf_and_strict_json_tuples() -> None:
    raw = b'{"schema_version":1,"values":["\\u65e5",2,1.5]}\n'
    result = _parse(raw)
    assert result.values == ("日", 2, 1.5)
    assert canonical_json_bytes(result) + b"\n" == raw


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":1,"schema_version":1,"values":[]}\n',
        b'{"schema_version":1,"values":[NaN]}\n',
        b'{"schema_version":1,"values":[Infinity]}\n',
        b'{"schema_version":1,"values":[-Infinity]}\n',
        b'{"schema_version":1,"values":[1e999]}\n',
        b'{"schema_version":true,"values":[]}\n',
        b'{"schema_version":1.0,"values":[]}\n',
        b'\xef\xbb\xbf{"schema_version":1,"values":[]}\n',
        b'{"schema_version":1,"values":["\xff"]}\n',
        b'{"schema_version":1,"values":["\\ud800"]}\n',
        b'{"schema_version":1,"values":[],"extra":"private-sentinel"}\n',
        b'{"values":[],"schema_version":1}\n',
        b'{"schema_version":1, "values":[]}\n',
        b'{"schema_version":1,"values":[]}',
        b'{"schema_version":1,"values":[]}\r\n',
        b'{"schema_version":1,"values":[]}\n\n',
    ],
)
def test_canonical_json_rejects_untrusted_bytes_without_normalizing_or_exposing_them(
    raw: bytes,
) -> None:
    with pytest.raises(ValueError) as failure:
        _parse(raw)
    assert str(failure.value) in {
        "invalid evidence JSON",
        "evidence is not canonical",
        "evidence model mismatch",
    }
    assert "private-sentinel" not in str(failure.value)
    assert failure.value.__cause__ is None


@pytest.mark.parametrize("boundary", ["size", "depth", "string", "tokens"])
def test_canonical_json_bounds_before_json_construction(
    monkeypatch: pytest.MonkeyPatch, boundary: str,
) -> None:
    parser = importlib.import_module("evaluation.evidence_json")
    raw = b'{"schema_version":1,"values":[]}\n'
    maximum = 100_000
    if boundary == "size":
        maximum = len(raw) - 1
    elif boundary == "depth":
        raw = b"[" * 33 + b"0" + b"]" * 33 + b"\n"
    elif boundary == "string":
        raw = b'{"schema_version":1,"values":["' + b"x" * 8191 + b'"]}\n'
    else:
        monkeypatch.setattr(parser, "_MAX_TOKENS", 8)

    def forbidden_loads(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("JSON construction must not occur beyond lexical bounds")

    monkeypatch.setattr(parser.json, "loads", forbidden_loads)
    with pytest.raises(ValueError, match="evidence .*limit"):
        parser.parse_canonical_model(raw, Evidence, maximum=maximum)


def test_canonical_json_rejects_actual_four_million_token_overflow_before_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = importlib.import_module("evaluation.evidence_json")
    raw = b"[" + b"0," * 2_000_000 + b"0]\n"

    def forbidden_loads(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("four million token overflow reached JSON construction")

    monkeypatch.setattr(parser.json, "loads", forbidden_loads)
    with pytest.raises(ValueError, match="evidence token limit"):
        parser.parse_canonical_model(raw, Evidence, maximum=8 * 1024 * 1024)


def test_canonical_json_accepts_exact_byte_and_string_limits() -> None:
    raw = b'{"schema_version":1,"values":["' + b"x" * 8190 + b'"]}\n'
    assert _parse(raw, len(raw)).values == ("x" * 8190,)


def test_canonical_json_rejects_model_serialization_changes() -> None:
    class Defaulted(BaseModel):
        required: str
        extra: int = 1

    parser = importlib.import_module("evaluation.evidence_json")
    with pytest.raises(ValueError, match="evidence model mismatch"):
        parser.parse_canonical_model(b'{"required":"synthetic"}\n', Defaulted, maximum=100)


def test_canonical_json_rejects_oversized_integer_with_sanitized_reason() -> None:
    raw = b'{"schema_version":1,"values":[' + b"9" * 5000 + b"]}\n"
    with pytest.raises(ValueError, match="invalid evidence JSON"):
        _parse(raw)


def test_canonical_json_depth_limit_includes_objects_and_ignores_escaped_strings() -> None:
    class Nested(BaseModel):
        value: Any

    parser = importlib.import_module("evaluation.evidence_json")
    value: Any = 'braces [ { and escaped " string'
    for _ in range(31):
        value = [value]
    raw = canonical_json_bytes({"value": value}) + b"\n"
    assert parser.parse_canonical_model(raw, Nested, maximum=10_000).value == value
    raw = canonical_json_bytes({"value": [value]}) + b"\n"
    with pytest.raises(ValueError, match="evidence structural limit"):
        parser.parse_canonical_model(raw, Nested, maximum=10_000)
    assert json.loads(raw)["value"] == [value]
