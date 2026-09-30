# Blinded Evaluation Module

## Purpose

The evaluation package runs D37 trials against the immutable D35 candidate without importing evaluation code into the production application. It converts approved D24 cases to a strict label-free wire format, supervises the external trial host, scores redacted observations, and publishes canonical protocol and aggregate artifacts. Real held-out inputs, token keys, and detailed evidence remain evaluator-controlled.

## Project position

Production `app` modules never import `evaluation`. The D37 runner invokes the D36 host, which starts candidate application interfaces in subprocesses. D38 and D40 consume the D37-owned result contract unchanged. Dependencies point from orchestration to contracts, scoring, filesystem, runtime, attestation, and sealing helpers; helpers do not import orchestration or application modules.

## Inputs and outputs

`run_blinded_evaluation(...)` receives detached candidate/freeze paths, corpus and approval paths, an external output root, model/index configuration, evaluator identity, and an external 32-byte token-key path. It returns `EvaluationResultBundle` and publishes immutable `protocol.json`, tool attestation, trial records, sealed detailed evidence, and `result-bundle.json`. Public artifacts contain only hashes, bounded counts, and opaque case/category tokens.

`write_run_protocol_exclusive(...)` preserves the existing runner API. `blinded_io` exports bounded regular-file reads, validated directory creation, atomic mutable writes, and immutable no-replace publication. `blinded_runtime` exports candidate-root validation, retained candidate anchors, process-tree supervision, and trial-host invocation.

## Dependencies and dependents

- `blinded_contracts` owns token and protocol models.
- `result_contracts` owns the D37–D40 aggregate and its 128 MiB maximum serialization bound.
- `blinded_scoring` consumes strict D24 cases and strict redacted observations.
- `blinded_io` uses only Python filesystem primitives.
- `blinded_runtime` imports `blinded_io` and uses asyncio, POSIX process groups, or Windows Job Objects.
- `blinded_runner` imports these modules and owns attestation, resume, ordering, and aggregation.
- D38/D40 depend on `result_contracts`; no evaluation module is a production dependency.

## Control and data flow

The runner validates source and candidate attestations, retains a candidate-directory identity, derives opaque topology, and publishes the protocol before any trial. Each included case/mode gets fresh evaluator storage. The runtime helper starts and tears down the trusted host process tree. The D36 host sends candidate-worker stdout/stderr to the null device, validates the redacted observation, and publishes no raw candidate output. The runner scores completed observations, writes immutable trial records, seals detailed evidence, validates aggregate equations, and publishes the bounded result bundle.

D24 `switch_target` changes only UI selection, then rereads the exact original request and response. It creates no replacement request and uses the normal single request/turn/receipt delta. Every primary, replay, confirmation, and duplicate response mode must equal the trial mode.

## Key decisions and limits

Protocol and result bundle caps are 64 MiB and 128 MiB respectively, each larger than an independently calculated maximum valid topology and used consistently for publication and readback. Stored media paths must be canonical relative POSIX paths; component and descriptor identities fail closed on links, reparses, special files, containment violations, or races. Missing media emits only the path hash. The design protects against cooperative path replacement, not a hostile same-user principal able to tamper with process memory or exploit unavoidable platform syscall gaps.

Candidate failures retain fixed classifications. Trusted-host logs remain bounded, but candidate stdout/stderr, prompts, bodies, and secrets are never persisted. A tooling-only fix changes D36/D37 attestations and requires regenerated downstream evidence without changing the D35 candidate.

## Relevant verification

Focused contracts and end-to-end synthetic coverage live in `backend/tests/test_d36_candidate_protocol.py` and `backend/tests/test_d37_blinded_runner.py`. Run those first, then backend pytest/Ruff and frontend test/build/lint gates sequentially. Tests use repository synthetic fixtures and fake providers only.
