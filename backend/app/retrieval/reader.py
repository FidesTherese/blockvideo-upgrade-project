"""Read-only verified index snapshot; no ranking, readiness or execution."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.retrieval.contracts import EmbeddingProfile, IndexBundle, IndexDocument, IndexManifest, SearchScope
from app.retrieval.serialization import RetrievalError, canonical, decode, digest, read_bytes
from app.retrieval.sources import IndexSources
from app.retrieval.vectors import validate_vectors


def check_sources(manifest: IndexManifest, sources: IndexSources) -> None:
    if (manifest.catalog_sha256 != sources.catalog_sha256
            or manifest.scope_sha256 != sources.scope_sha256
            or manifest.catalog_semantic_sha256 != sources.catalog_semantic_sha256
            or manifest.app_id != sources.app_id
            or manifest.operation_count != sources.operation_count):
        raise RetrievalError("stale_index")


@dataclass(frozen=True)
class VerifiedIndex:
    manifest: IndexManifest
    bundle: IndexBundle

    def eligible_documents(self, scope: SearchScope, current_sources: IndexSources) -> tuple[IndexDocument, ...]:
        """Recheck current source fingerprints before every later candidate lookup."""
        check_sources(self.manifest, current_sources)
        scope = SearchScope.model_validate(scope.model_dump())
        if scope.app_id != self.manifest.app_id:
            return ()
        requested = {ref.key for ref in scope.operations}
        known = {doc.key for doc in self.bundle.documents}
        if len(requested) != len(scope.operations) or requested - known:
            raise RetrievalError("unknown_or_duplicate_scope_operation")
        capabilities = set(scope.capabilities)
        return tuple(doc for doc in self.bundle.documents
                     if doc.key in requested and set(doc.required_capabilities) <= capabilities)


def load_index(directory: Path, sources: IndexSources, profile: EmbeddingProfile) -> VerifiedIndex:
    """A manifest is read once; its digest names one immutable bundle."""
    try:
        raw = decode(read_bytes(directory / "manifest.json", 64_000))
        if not isinstance(raw, dict) or type(raw.get("format_version")) is not int:
            raise RetrievalError("invalid_manifest")
        manifest = IndexManifest.model_validate(raw)
        check_sources(manifest, sources)
        if manifest.profile != profile:
            raise RetrievalError("embedding_profile_mismatch")
        payload = read_bytes(directory / f"bundle-{manifest.bundle_sha256}.json", 64_000_000)
        if digest(payload) != manifest.bundle_sha256:
            raise RetrievalError("bundle_hash_mismatch")
        bundle = IndexBundle.model_validate(decode(payload))
        documents_json = [d.model_dump(mode="json") for d in bundle.documents]
        if (len(bundle.documents) != manifest.document_count
                or digest(canonical(documents_json)) != manifest.documents_sha256
                or digest(canonical(bundle.vectors)) != manifest.vectors_sha256):
            raise RetrievalError("content_hash_mismatch")
        # Re-derive public text and exact versions. A self-consistent forged
        # manifest with a wrong ID/version/schema/scope must still fail.
        if bundle.documents != sources.documents:
            raise RetrievalError("documents_source_mismatch")
        validate_vectors(bundle.vectors, len(bundle.documents), profile.dimensions)
        return VerifiedIndex(manifest, bundle)
    except (ValidationError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise RetrievalError("invalid_index") from None
