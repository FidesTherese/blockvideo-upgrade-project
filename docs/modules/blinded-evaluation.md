# Blinded Evaluation Module

## Purpose

The evaluation package runs D37 blinded trials against the immutable D35 candidate and imports only their public aggregate through D38. It converts approved cases to a label-free format, supervises the external host and publishes canonical protocol/results. Production never imports evaluation tooling; real inputs, keys and detailed evidence remain evaluator-controlled.

## Project position

The D37 runner invokes D36's candidate-rooted subprocess host. D38 consumes unchanged D37 contracts. D39 foundations and Task 2's fixed verifier are implemented; Task 3 smokes, full attestation, operational acceptance and D40 remain deferred. D38 imports contracts, canonical parsing, filesystem and attestation helpers, never later executors. D39 controllers import no application, private corpus, D37 runner or D38 importer.

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

## D39 foundation

`smoke_contracts` owns frozen schemas/inventory, imported unchanged. The materializer copies readonly source with identity-bound, resumable cleanup. Owned scopes gate isolated native base Python before Job/session registration, cap shared output at 2 MiB and confirm descendant/reader teardown.

`release_verification.verify_release_candidate(...)` validates materialization/six smoke receipts, then derives distinct backend/frontend source-only groups. It proves native tool origins and contains writable configuration. Missing extras/esbuild stops execution without resync/rebuild/lock repair. One executor thread keeps memory monitoring runnable during blocking hashes/Git checks. Four bounded scan rules report counts only. Finally cleans groups/runtime before native two-artifact publication. Cleanup loss remains failed, never deleting replacements. Missing Task 3 files block the literal 19-file attestation, never reduce it; rejection still attempts bound runtime cleanup. Failed evidence retains actual prefixes/nulls.

## Key decisions and limits

Protocol/result caps are 64/128 MiB, used for publication/readback. The scanner's 8,000,000-token cap admits the proven maximum bundle of 4,980,838 tokens; 65,535-case/category fixtures prove canonical roundtrip without relaxing depth/string/type/accounting restrictions. Stored media paths must be canonical relative POSIX paths; component and descriptor identities fail closed on links, reparses, special files, containment violations, or races. Missing media emits only the path hash. The design protects against cooperative path replacement, not a hostile same-user principal able to tamper with process memory or exploit unavoidable platform syscall gaps.

Index files stream in 1 MiB chunks with pre/open/post identity checks, at most 4,096 files and 512 MiB total; manifest/blob caps are decimal 64,000/64,000,000 bytes. Tool-source fingerprints separately cap each file at 8 MiB before reading and each attestation inventory at 512 MiB, with streamed pre/open/post identity checks. Result and runner category denominator tallies are single-pass; all existing equations, fields and accepted positive bytes are preserved.

Candidate failures retain fixed classifications. Trusted-host logs remain bounded, but candidate stdout/stderr, prompts, bodies, and secrets are never persisted. A tooling-only fix changes D36/D37 attestations and requires regenerated downstream evidence without changing the D35 candidate.

## Relevant verification

Focused tests are `backend/tests/test_d36_candidate_protocol.py`, `test_d37_blinded_runner.py`, `test_d38_result_import.py`, `test_d39_release_verification.py`, `test_d39_verifier_driver.py` and `test_evidence_json.py`. D39 checks use sequential 768 MiB Jobs with resident monitoring and explicit platform skips. Task 2 covers real Git/index bypasses, native Python/Node/npx seams, bounded scans, failed prefixes, source/freeze drift, replacement refusal and cleanup/publication. Installation-boundary doubles and typed passed fixtures are not operational acceptance. `tests/d37_pinned_support.py` verifies D35 blobs and synthetic index binding, not real evaluation, weights or human review. Backend/frontend gates remain deferred.
