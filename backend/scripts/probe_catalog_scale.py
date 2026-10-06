"""Unofficial scale probe: real retrieval and a real model on a 10- vs 1,010-operation catalog.

Interpretation only; nothing executes. The 1,000 synthetic operations are video-like
distractors ("冒頭のBGMの音量を設定して" ...) that share vocabulary with the real
operations, so the probe is harder than unrelated business distractors. Uses public
development cases only and the fixed local E5 embedding profile.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from app.interpretation.contracts import (CandidateRef, DialogueContextTurn, InterpretationInput, MinimalState,
                                          OperationProposal)
from app.interpretation.local_chat import LocalChatAdapter
from app.language_operations.intent_guard import negative_control_reason
from app.operations.catalog import load_catalog
from app.retrieval.builder import publish_index
from app.retrieval.contracts import EmbeddingProfile
from app.retrieval.onnx_embeddings import OnnxEmbeddingAdapter
from app.retrieval.reader import load_index
from app.retrieval.sources import DEFAULT_CATALOG, DEFAULT_SCOPE, load_sources
from app.semantic_interpretation.service import SemanticInterpreter
from evaluation import corpus
from evaluation.contracts import Case

BACKEND = Path(__file__).resolve().parents[1]
DISTRACTORS = 1000
SUBJECTS = ("BGMの音量", "サムネイル", "字幕の色", "字幕の位置", "背景画像", "透かし", "章タイトル",
            "エンディング", "字幕のフォント", "書き出し解像度")
VERBS = ("設定", "確認", "削除", "書き出し", "複製", "追加", "並べ替え", "共有", "予約", "一覧表示")
SCOPES = ("ブロック1", "ブロック2", "冒頭", "末尾", "全ブロック", "下書き", "テンプレート", "共有リンク",
          "別プロジェクト", "公開版")


def phrase(index: int) -> str:
    return f"{SCOPES[index // 100]}の{SUBJECTS[index % 10]}を{VERBS[(index // 10) % 10]}して"


def write_scaled_catalog(root: Path) -> None:
    """Copy the real catalog files into ``root`` and add the synthetic distractors."""
    for name in ("definitions.json", "search_scope.json", "operation_annotations.json"):
        shutil.copy(DEFAULT_CATALOG.with_name(name), root / name)
    definitions = json.loads((root / "definitions.json").read_text(encoding="utf-8"))
    scope = json.loads((root / "search_scope.json").read_text(encoding="utf-8"))
    annotations = json.loads((root / "operation_annotations.json").read_text(encoding="utf-8"))
    template = next(item for item in definitions["operations"] if item["operation_id"] == "project.status.get")
    for index in range(DISTRACTORS):
        operation_id = f"project.distractor-{index:04d}.run"
        definitions["operations"].append({**template, "operation_id": operation_id,
                                          "description": f"Video project tool: {phrase(index)}",
                                          "examples": [phrase(index)]})
        scope["bindings"].append({"operation_id": operation_id, "operation_version": 1,
                                  "required_capabilities": ["project.status.read"]})
        annotations["operations"][operation_id] = {"utterances": [phrase(index)]}
    definitions["operations"].sort(key=lambda item: (item["operation_id"], item["operation_version"]))
    scope["bindings"].sort(key=lambda item: (item["operation_id"], item["operation_version"]))
    for name, value in (("definitions.json", definitions), ("search_scope.json", scope),
                        ("operation_annotations.json", annotations)):
        (root / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def sample_cases(path: Path, limit: int) -> list[Case]:
    """Round-robin over expected interpretation kinds; development cases only."""
    groups: dict[str, list[Case]] = collections.defaultdict(list)
    for case in corpus.load_cases(path):
        if case.split != "development":
            raise ValueError("scale probe refuses held-out material")
        if case.expected.interpretation != "not_called":
            groups[case.expected.interpretation].append(case)
    chosen: list[Case] = []
    while len(chosen) < limit and any(groups.values()):
        for key in sorted(groups):
            if groups[key] and len(chosen) < limit:
                chosen.append(groups[key].pop(0))
    return chosen


def _request(case: Case, refs: tuple[CandidateRef, ...]) -> InterpretationInput:
    turns = tuple(DialogueContextTurn.model_validate({key: value for key, value in turn.items()
                                                      if key in DialogueContextTurn.model_fields})
                  for turn in case.initial.prior_turns)
    return InterpretationInput(text=case.request.text, candidates=refs, dialogue=turns, state=MinimalState(
        selected_project_id=case.initial.project_id, revision=case.initial.revision,
        subtitle_font_size=case.initial.settings.get("subtitle_font_size"), status=case.initial.project_status))


async def _run_catalog(name: str, catalog_path: Path, scope_path: Path, cases: list[Case], encoder: Any,
                       profile: EmbeddingProfile, args: argparse.Namespace) -> dict[str, Any]:
    sources = load_sources(catalog_path, scope_path)
    index_dir = Path(tempfile.mkdtemp())
    started = time.perf_counter()
    publish_index(index_dir, sources, profile, await encoder.embed_documents(tuple(d.text for d in sources.documents)))
    build_seconds = round(time.perf_counter() - started, 1)
    catalog = load_catalog(catalog_path)
    refs = tuple(CandidateRef(operation_id=d.operation_id, operation_version=d.operation_version)
                 for d in catalog.definitions)
    interpreter = SemanticInterpreter(lambda s: load_index(index_dir, s, profile),
                                      lambda: load_sources(catalog_path, scope_path), encoder)
    totals: collections.Counter[str] = collections.Counter()
    rows = []
    for case in cases:
        case_started = time.perf_counter()
        async with LocalChatAdapter(args.base_url, args.model, timeout_seconds=180, reasoning_effort="none") as chat:
            result = await interpreter.preview(catalog, chat, _request(case, refs))
        proposal = result.interpretation.proposal
        kind = proposal.kind if proposal is not None else "error"
        if isinstance(proposal, OperationProposal) and negative_control_reason(case.request.text, proposal.operation_id):
            kind = "no_operation"
        expected = {item.operation_id for item in case.expected.operations}
        offered = {candidate.operation_id for candidate in result.candidates}
        chosen = getattr(proposal, "operation_id", None)
        totals["cases"] += 1
        totals["class_match"] += int(kind == case.expected.interpretation)
        totals["distractor_chosen"] += int(bool(chosen and "distractor" in chosen))
        if expected:
            totals["operation_cases"] += 1
            totals["expected_offered"] += int(bool(expected & offered))
            totals["operation_id_match"] += int(chosen in expected)
        totals["chat_calls"] += result.trace.chat_calls
        totals["ms"] += round((time.perf_counter() - case_started) * 1000)
        rows.append({"case": case.case_id, "expected": case.expected.interpretation, "got": kind, "operation": chosen,
                     "stages": [stage.name for stage in result.trace.stages]})
    summary: dict[str, Any] = {key: totals[key] for key in ("cases", "class_match", "operation_cases",
                                                            "expected_offered", "operation_id_match",
                                                            "distractor_chosen", "chat_calls")}
    summary.update(avg_seconds=round(totals["ms"] / max(1, totals["cases"]) / 1000, 1), operations=len(refs),
                   documents=len(sources.documents), index_build_seconds=build_seconds)
    return {"catalog": name, "summary": summary, "rows": rows}


async def run(args: argparse.Namespace) -> dict[str, Any]:
    profile = EmbeddingProfile.model_validate_json(args.profile.read_bytes())
    cases = sample_cases(args.cases, args.limit)
    work = Path(tempfile.mkdtemp())
    write_scaled_catalog(work)
    results = []
    async with OnnxEmbeddingAdapter(profile, args.assets) as encoder:
        results.append(await _run_catalog("real", DEFAULT_CATALOG, DEFAULT_SCOPE, cases, encoder, profile, args))
        results.append(await _run_catalog("scaled", work / "definitions.json", work / "search_scope.json",
                                          cases, encoder, profile, args))
    return {"unofficial": True, "model": args.model, "held_out_used": False, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--cases", type=Path, default=BACKEND.parent / "evaluation/d24/development.jsonl")
    parser.add_argument("--profile", type=Path, default=BACKEND / "app/retrieval/e5-profile.json")
    parser.add_argument("--assets", type=Path, default=BACKEND / "storage/embedding-models/multilingual-e5-small")
    parser.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("use a new output file")
    result = asyncio.run(run(args))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for item in result["results"]:
        print(item["catalog"], json.dumps(item["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
