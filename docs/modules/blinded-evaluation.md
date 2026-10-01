# Blinded Evaluation Module

## Purpose

Evaluation runs approved label-free D37 trials against immutable D35, supervises their host and publishes canonical protocol/results. D38 imports only public aggregates. Production never imports evaluation; private inputs/keys/evidence remain evaluator-controlled.

## Project position

The D37 runner invokes D36's candidate-rooted subprocess host. D38 consumes unchanged D37 contracts. D39 foundations, the fixed verifier and Task 3 smoke source are implemented; Task 3 review, clean-source attestation, operational acceptance and D40 remain pending. D38 imports contracts, canonical parsing, filesystem and attestation helpers, never later executors. D39 controllers import no application, private corpus, D37 runner or D38 importer.

## Inputs and outputs

`run_blinded_evaluation(...)` receives candidate/freeze, approved corpus, external output, model/index configuration, evaluator identity and external token key. Optional paired embedding profile/base URL go only to stateful hosts. Profile containment, identity, index agreement and loopback transport are checked by runner and host. It returns `EvaluationResultBundle` and publishes immutable protocol, attestation, trials, sealed evidence and aggregate. Public artifacts contain only hashes, counts and opaque tokens.

`write_run_protocol_exclusive(...)` preserves the existing runner API. `blinded_io` exports bounded regular-file reads, streamed blob fingerprints, validated directory creation, atomic mutable writes, and immutable no-replace publication. The pure `evidence_json.parse_canonical_model(raw, model_type, *, maximum)` rejects lexical depth/token/string overflow before JSON construction, duplicates/nonfinite values, invalid encoding and noncanonical raw/model bytes with fixed sanitized reasons. `blinded_runtime` exports candidate-root validation, retained candidate anchors, process-tree supervision, and trial-host invocation.

`import_evaluation_result(...)` receives public bundle/protocol, completed D36 publication, upstream source attestations and an out-of-band digest. It returns strict `ImportValidation` and publishes unchanged accepted bytes, validation and its own clean-HEAD 25-path attestation as one new directory. It never opens/enumerates sealed evidence. Its fixed redacted CLI exits 2 on refusal.

## Dependencies and dependents

- `blinded_contracts` owns token and protocol models.
- `result_contracts` owns the D37–D40 aggregate and its 128 MiB maximum serialization bound.
- `blinded_scoring` consumes strict D24 cases and strict redacted observations.
- `evidence_json` depends only on stdlib, Pydantic and attestation canonicalization; it never imports application, runner or schema classes.
- `blinded_io` reuses D36 native anchors/no-replace rename for the filesystem-only accepted triplet, not its marker-specific candidate publisher.
- The D36 host uses shared parser/IO outside candidate bootstrap; inventories bind these helpers and D37 operator-validation contracts.
- `blinded_runtime` imports `blinded_io` and uses asyncio, POSIX process groups, or Windows Job Objects.
- `blinded_runner` imports these modules and owns attestation, resume, ordering, and aggregation.
- D38/D40 depend on `result_contracts`; no evaluation module is a production dependency.

## Control and data flow

The runner validates source and candidate attestations, retains a candidate-directory identity, derives opaque topology, and publishes the protocol before any trial. Each included case/mode gets fresh evaluator storage. The runtime helper starts and tears down the trusted host process tree. The D36 host sends candidate-worker stdout/stderr to the null device, validates the redacted observation, and publishes no raw candidate output. The runner scores completed observations, writes immutable trial records, seals detailed evidence, validates aggregate equations, and publishes the bounded result bundle.

D24 `switch_target` changes selection, then rereads the original request/response without replacement. Every response mode must equal the trial mode.

D38 verifies detached/canonical bytes, historical recorded Git blobs, identity chains and exact token/category accounting before clean current-source attestation and no-replace publication. Existing finals are refused; lost ownership or faults never authorize pathname cleanup.

## D39 foundation

`smoke_contracts` owns frozen schemas/inventory, imported unchanged. The materializer copies readonly source with identity-bound, resumable cleanup. Owned scopes gate isolated native base Python before Job/session registration, cap shared output at 2 MiB and confirm descendant/reader teardown.

`release_verification.verify_release_candidate(...)` validates materialization/six smoke receipts, then derives distinct backend/frontend source-only groups. It proves native tool origins and contains writable configuration. Missing extras/esbuild stops execution without resync/rebuild/lock repair. One executor thread keeps memory monitoring runnable during blocking hashes/Git checks. Four bounded scan rules report counts only. Finally cleans groups/runtime before native two-artifact publication. Cleanup loss remains failed, never deleting replacements. The literal 19-file attestation requires clean committed smoke source, never a reduced closure; rejection still attempts bound runtime cleanup. Failed evidence retains actual prefixes/nulls.

`scripts.d39_smoke.run_candidate_smokes(...)` owns a separate fresh group and six typed stages. The fixed candidate bootstrap binds settings before imports and uses candidate migration, restore, retrieval and generation APIs. Standalone `browser_smoke` runs with sandbox Python/websockets, a new owned native browser, tagged loopback servers and bounded CDP. Synthetic speaker discovery uses the owned fake provider. Media is 320x240/12 fps; artifact hashes match actual publication. Stage failures retain only actual receipts; drift blocks receipt binding. Group teardown leaves readonly runtime for verifier/explicit cleanup. Administrative stop permits scope reuse after confirmed teardown without changing termination codes or clearing failures. The README prerequisite subcheck stays failed.

## Key decisions and limits

Protocol/result caps are 64/128 MiB. The 8,000,000-token limit admits the measured maximum bundle without relaxing depth/string/type/accounting checks. Stored media paths are canonical relative POSIX paths; identities reject links, reparses, special files, escapes and observed races. Missing media emits only its path hash. Cooperative replacement is covered; hostile same-user memory/syscall-gap tampering is not.

Index/source hashing uses bounded streams and pre/open/post identity checks; exact file/count/byte limits are in the DTD. Category tallies are single-pass; aggregate equations and accepted bytes are unchanged.

Candidate failures retain fixed classifications. Trusted-host logs remain bounded, but candidate stdout/stderr, prompts, bodies, and secrets are never persisted. A tooling-only fix changes D36/D37 attestations and requires regenerated downstream evidence without changing the D35 candidate.

## Relevant verification

Focused tests are `backend/tests/test_d36_candidate_protocol.py`, `test_d37_blinded_runner.py`, `test_d38_result_import.py`, `test_d39_release_verification.py`, `test_d39_verifier_driver.py`, `test_d39_smoke.py` and `test_evidence_json.py`. D39 checks use sequential 768 MiB Jobs with resident monitoring and explicit platform skips. Task 2 covers real Git/index bypasses, native Python/Node/npx seams, bounded scans, failed prefixes, source/freeze drift, replacement refusal and cleanup/publication. Installation-boundary doubles and typed passed fixtures are not operational acceptance. `tests/d37_pinned_support.py` verifies D35 blobs and synthetic index binding, not real evaluation, weights or human review. Current smoke checks have 34 passes, including genuine pinned-candidate migration/restore, index/both modes and real fake-provider FFmpeg/ffprobe. Driver/transport doubles are not full-browser acceptance. A selected native rerun has 11 passes and 10 memory-preflight failures. Independent review is worker-model blocked; fresh/full backend/frontend/browser gates remain pending.
