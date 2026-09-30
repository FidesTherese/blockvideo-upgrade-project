# Blinded Evaluation Module

## Purpose

The evaluation package runs D37 blinded trials against the immutable D35 candidate and imports only their public aggregate through D38. It converts approved cases to a label-free format, supervises the external host and publishes canonical protocol/results. Production never imports evaluation tooling; real inputs, keys and detailed evidence remain evaluator-controlled.

## Project position

The D37 runner invokes the D36 host, which starts candidate application interfaces in subprocesses. D38 consumes unchanged D37 contracts; D40 remains planned. D38 imports contracts, canonical parsing, filesystem and attestation helpers, never the runner or later executors. Shared contract imports account for the attested app-contract closure.

## Inputs and outputs

`run_blinded_evaluation(...)` receives detached candidate/freeze paths, corpus and approval paths, an external output root, model/index configuration, evaluator identity, an external 32-byte token-key path, and optional paired `embedding_profile`/`embedding_base_url` operator parameters. Only stateful host calls receive the pair; the profile must be external, regular/non-link, <=16,000 bytes and use the local HTTP transport with a loopback `/v1` endpoint. The runner protects the profile parent and checks index/profile equality before publication or resume; the host repeats those checks and binds profile identity across execution. It returns `EvaluationResultBundle` and publishes immutable `protocol.json`, tool attestation, trial records, sealed detailed evidence, and `result-bundle.json`. Public artifacts contain only hashes, bounded counts, and opaque case/category tokens.

`write_run_protocol_exclusive(...)` preserves the existing runner API. `blinded_io` exports bounded regular-file reads, streamed blob fingerprints, validated directory creation, atomic mutable writes, and immutable no-replace publication. The pure `evidence_json.parse_canonical_model(raw, model_type, *, maximum)` rejects lexical depth/token/string overflow before JSON construction, duplicates/nonfinite values, invalid encoding and noncanonical raw/model bytes with fixed sanitized reasons. `blinded_runtime` exports candidate-root validation, retained candidate anchors, process-tree supervision, and trial-host invocation.

`import_evaluation_result(...)` receives public bundle/protocol, completed D36 publication, upstream source attestations and an out-of-band digest. It returns strict `ImportValidation` and publishes unchanged accepted bytes, validation and its own clean-HEAD 25-path attestation as one new directory. It never opens/enumerates sealed evidence. Its fixed redacted CLI exits 2 on refusal.

## Dependencies and dependents

- `blinded_contracts` owns token and protocol models.
- `result_contracts` owns the D37–D40 aggregate and its 128 MiB maximum serialization bound.
- `blinded_scoring` consumes strict D24 cases and strict redacted observations.
- `evidence_json` depends only on stdlib, Pydantic and attestation canonicalization; it never imports application, runner or schema classes.
- `blinded_io` reuses D36 native anchors/no-replace rename for the filesystem-only accepted triplet, not its marker-specific candidate publisher.
- The D36 host imports the shared parser/IO only in host-side functions; its candidate-rooted bootstrap does not import the candidate's outdated evaluation package. The fixed D36 source inventories include both new dependencies; the conservative D37 inventory also binds operator-validation application contracts.
- `blinded_runtime` imports `blinded_io` and uses asyncio, POSIX process groups, or Windows Job Objects.
- `blinded_runner` imports these modules and owns attestation, resume, ordering, and aggregation.
- D38/D40 depend on `result_contracts`; no evaluation module is a production dependency.

## Control and data flow

The runner validates source and candidate attestations, retains a candidate-directory identity, derives opaque topology, and publishes the protocol before any trial. Each included case/mode gets fresh evaluator storage. The runtime helper starts and tears down the trusted host process tree. The D36 host sends candidate-worker stdout/stderr to the null device, validates the redacted observation, and publishes no raw candidate output. The runner scores completed observations, writes immutable trial records, seals detailed evidence, validates aggregate equations, and publishes the bounded result bundle.

D24 `switch_target` changes selection, then rereads the original request/response without replacement. Every response mode must equal the trial mode.

D38 verifies detached/canonical bytes, historical recorded Git blobs, identity chains and exact token/category accounting before clean current-source attestation and no-replace publication. Existing finals are refused; lost ownership or faults never authorize pathname cleanup.

## Key decisions and limits

Protocol/result caps are 64/128 MiB, used for publication/readback. The scanner's 8,000,000-token cap admits the proven maximum bundle of 4,980,838 tokens; 65,535-case/category fixtures prove canonical roundtrip without relaxing depth/string/type/accounting restrictions. Stored media paths must be canonical relative POSIX paths; component and descriptor identities fail closed on links, reparses, special files, containment violations, or races. Missing media emits only the path hash. The design protects against cooperative path replacement, not a hostile same-user principal able to tamper with process memory or exploit unavoidable platform syscall gaps.

Index files stream in 1 MiB chunks with pre/open/post identity checks, at most 4,096 files and 512 MiB total; manifest/blob caps are decimal 64,000/64,000,000 bytes. Tool-source fingerprints separately cap each file at 8 MiB before reading and each attestation inventory at 512 MiB, with streamed pre/open/post identity checks. Result and runner category denominator tallies are single-pass; all existing equations, fields and accepted positive bytes are preserved.

Candidate failures retain fixed classifications. Trusted-host logs remain bounded, but candidate stdout/stderr, prompts, bodies, and secrets are never persisted. A tooling-only fix changes D36/D37 attestations and requires regenerated downstream evidence without changing the D35 candidate.

## Relevant verification

Focused synthetic coverage lives in `backend/tests/test_d36_candidate_protocol.py`, `test_d37_blinded_runner.py` and `test_d38_result_import.py`. Run those first, then backend pytest/Ruff and frontend test/build/lint gates sequentially. Tests use repository synthetic fixtures and fake providers only. `test_evidence_json.py` is the standalone pure-parser boundary. `tests/d37_pinned_support.py` verifies every exact-D35 archive blob and builds/loads an external synthetic source/profile index in candidate-rooted subprocesses. Pinned tests cover both modes, restart resend, original-target preservation, actual retrieval (not fallback-only), unchanged complete source/index hashes and invalid-index negatives. This is not real evaluation, optional ONNX proof or independent acceptance.
