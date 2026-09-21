"""Exact cosine ranking of distinct operation versions, never executable requests."""
from __future__ import annotations

from pydantic import Field

from app.retrieval.contracts import OperationRef, Scalar, SearchScope
from app.retrieval.reader import VerifiedIndex
from app.retrieval.sources import IndexSources
from app.retrieval.vectors import normalize_vector


class RankedCandidate(OperationRef):
    score: Scalar = Field(ge=-1, le=1)
    document_id: str = Field(max_length=200)


def rank_operations(index: VerifiedIndex, vector: tuple[float, ...], scope: SearchScope,
                    current_sources: IndexSources) -> tuple[RankedCandidate, ...]:
    """Maximum document score per exact operation; ties have a stable ID order."""
    query = normalize_vector(vector, index.manifest.profile.dimensions)
    eligible = {d.document_id for d in index.eligible_documents(scope, current_sources)}
    best: dict[tuple[str, int], RankedCandidate] = {}
    for document, other in zip(index.bundle.documents, index.bundle.vectors, strict=True):
        if document.document_id not in eligible:
            continue
        score = max(-1.0, min(1.0, sum(x * y for x, y in zip(query, other, strict=True))))
        candidate = RankedCandidate(operation_id=document.operation_id,
            operation_version=document.operation_version, score=score, document_id=document.document_id)
        previous = best.get(document.key)
        if previous is None or (-score, document.document_id) < (-previous.score, previous.document_id):
            best[document.key] = candidate
    return tuple(sorted(best.values(), key=lambda c: (-c.score, c.operation_id, c.operation_version)))
