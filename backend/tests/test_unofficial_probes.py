"""Unofficial development probes: no held-out material, labelled, reproducible inputs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.retrieval.sources import load_sources
from evaluation.development_probe import unreviewed_development
from scripts.probe_catalog_scale import DISTRACTORS, phrase, sample_cases, write_scaled_catalog

DEVELOPMENT = Path(__file__).parents[2] / "evaluation/d24/development.jsonl"


def test_unreviewed_development_is_labelled_and_refuses_held_out(tmp_path: Path) -> None:
    cases, gate = unreviewed_development(DEVELOPMENT)
    assert gate["unofficial"] is True and gate["approval_gate"] == "skipped" and len(cases) == gate["total"]
    held_out = tmp_path / "mixed.jsonl"
    lines = DEVELOPMENT.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["split"] = "held_out"
    held_out.write_text("\n".join([json.dumps(first, ensure_ascii=False), *lines[1:]]), encoding="utf-8")
    with pytest.raises(ValueError):
        unreviewed_development(held_out)


def test_scaled_catalog_adds_distinct_video_like_distractors(tmp_path: Path) -> None:
    write_scaled_catalog(tmp_path)
    sources = load_sources(tmp_path / "definitions.json", tmp_path / "search_scope.json")
    assert sources.operation_count == 10 + DISTRACTORS
    assert len({phrase(index) for index in range(DISTRACTORS)}) == DISTRACTORS


def test_sampled_cases_cover_each_interpretation_kind() -> None:
    cases = sample_cases(DEVELOPMENT, 12)
    assert len(cases) == 12
    assert len({case.expected.interpretation for case in cases}) >= 4
