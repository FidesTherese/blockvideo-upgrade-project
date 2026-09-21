"""Explicit developer-only publication; serving and models never call this module."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.retrieval.contracts import EmbeddingProfile, IndexBundle, IndexManifest
from app.retrieval.serialization import RetrievalError, canonical, digest, read_bytes
from app.retrieval.sources import IndexSources
from app.retrieval.vectors import validate_vectors


def _atomic_write(path: Path, data: bytes) -> None:
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".index-", suffix=".tmp", delete=False) as stream:
            temporary = stream.name
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def publish_index(directory: Path, sources: IndexSources, profile: EmbeddingProfile,
                  vectors: tuple[tuple[float, ...], ...]) -> IndexManifest:
    """Publish last; failure leaves an older manifest usable or the index absent."""
    validate_vectors(vectors, len(sources.documents), profile.dimensions)
    bundle = IndexBundle(documents=sources.documents, vectors=vectors)
    payload = canonical(bundle.model_dump(mode="json"))
    if len(payload) > 64_000_000:
        raise RetrievalError("index_too_large")
    manifest = IndexManifest(
        created_at=datetime.now(timezone.utc).isoformat(), app_id=sources.app_id,
        catalog_sha256=sources.catalog_sha256, scope_sha256=sources.scope_sha256,
        catalog_semantic_sha256=sources.catalog_semantic_sha256, profile=profile,
        operation_count=sources.operation_count, document_count=len(sources.documents),
        documents_sha256=digest(canonical([d.model_dump(mode="json") for d in sources.documents])),
        vectors_sha256=digest(canonical(vectors)), bundle_sha256=digest(payload),
    )
    try:
        directory.mkdir(parents=True, exist_ok=True)
        bundle_path = directory / f"bundle-{manifest.bundle_sha256}.json"
        if bundle_path.exists():
            if read_bytes(bundle_path, 64_000_000) != payload:
                raise RetrievalError("existing_bundle_corrupt")
        else:
            _atomic_write(bundle_path, payload)
        _atomic_write(directory / "manifest.json", canonical(manifest.model_dump(mode="json")))
    except OSError:
        raise RetrievalError("index_write_failed") from None
    return manifest
