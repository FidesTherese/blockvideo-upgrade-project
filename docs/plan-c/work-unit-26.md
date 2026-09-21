# D26 — Rebuildable operation vector index

The user authorized D26 after D25's technical checks. They selected the existing
Nomic Embed Text v1.5 for index lifecycle verification; Japanese retrieval quality
and multilingual model selection remain D27. Use local JSON storage with exact
cosine comparison planned for D27, not a vector database for nine definitions.

Generate descriptions, examples and bounded input-schema chunks from the existing
canonical definitions. A Git-managed search scope adds only application and
capability bindings for exact operation versions; it never duplicates schemas or
handler rules. Missing, duplicate and unknown bindings fail. Readiness, jobs,
credentials and project state are not indexing/filtering inputs.

Store source hashes, extraction/build format versions, model ID, local weights
SHA-256, dimension, document/query prefixes, normalization, document and vector
hashes in a manifest. A content-addressed immutable bundle is written first;
atomic manifest replacement publishes it last. Readers verify the whole bundle
against current source definitions and expected embedding configuration. A stale
source, version, unknown ID, tampered metadata or incompatible model fails closed.
Hashes detect mismatch/corruption; they are not signatures against a local writer
who can replace both the manifest and bundle.

Only an explicitly invoked developer CLI writes the index. The model receives
public operation documents and returns vectors only; it has no file paths, update
tool, handler, DB or application execution access. The reader exposes exact scoped
documents, not executable requests. Before later use, validate freshness against
the current catalog; the interpreter/core still resolve exact IDs and versions.

D26 does not wire retrieval into the existing All Tools UI. D27 adds ranking and
bounded fallback, D28 adds readiness presentation, D29 adds comparison modes.
No held-out text/labels or D24 approval changes. No new dependencies or downloads.

Verification: deterministic reconstruction, changed definitions including unchanged
version, missing/unknown IDs and versions, scope/capability isolation without
readiness filtering, corrupt/partial bundles, embedding response shape and identity,
failure during rebuild, real Nomic generation and offline validation. Run focused
tests then the repository-required backend/frontend regression checks. UI/media
behavior is unchanged; no new UI acceptance or semantic-accuracy claim is made.
