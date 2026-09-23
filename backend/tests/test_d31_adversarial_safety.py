from __future__ import annotations

import pytest

from app.language_operations.intent_guard import negative_control_reason, normalized_intent


@pytest.mark.parametrize(("raw", "expected"), [
    ("  ジョブ７を\u3000再試行しないで  ", "ジョブ7を 再試行しないで"),
    ("DON’T   RETRY job 7", "don't retry job 7"),
])
def test_normalized_intent(raw: str, expected: str) -> None:
    assert normalized_intent(raw) == expected


@pytest.mark.parametrize(("text", "operation_id", "expected"), [
    ("ジョブ7は再試行しないで", "project.generation.retry", "explicit_negative_intent"),
    ("ジョブ7は再試行しないで", "project.generation.cancel", None),
    ("キャンセルしないで", "project.generation.cancel", "explicit_negative_intent"),
    ("動画を生成しないで", "project.generation.start", "explicit_negative_intent"),
    ("何もしないで", "project.settings.update", "explicit_negative_intent"),
    ("字幕を56pxにして", "project.settings.update", None),
    ("Do not retry job 7", "project.generation.retry", "explicit_negative_intent"),
    ("DON’T RETRY job 7", "project.generation.retry", "explicit_negative_intent"),
    ("Do not cancel job 7", "project.generation.cancel", "explicit_negative_intent"),
    ("Don't cancel job 7", "project.generation.cancel", "explicit_negative_intent"),
    ("Do not generate a video", "project.generation.start", "explicit_negative_intent"),
    ("Don't generate a video", "project.generation.start", "explicit_negative_intent"),
    ("Do nothing", "project.settings.update", "explicit_negative_intent"),
    ("Do not execute", "project.settings.restore", "explicit_negative_intent"),
    ("Don't execute", "project.subtitle-font-size.set", "explicit_negative_intent"),
    ("ジョブ7を再試行して", "project.generation.retry", None),
    ("Retry job 7", "project.generation.retry", None),
    ("何もしないで", "project.status.get", None),
])
def test_negative_control_reason(text: str, operation_id: str, expected: str | None) -> None:
    assert negative_control_reason(text, operation_id) == expected
