# D36 Work Report — Exact D35 Release-Candidate Freeze

## Result

D36 freezes the clean D35 delivery commit
`522775516c0797abdb313e3432339a3a444b7ae2`
(`[DONE] Mission 35 Add recovery-oriented operational UI`). The canonical external
control is `../blockvideo-d36-control/d35-candidate.json`; its separately supplied and
recomputed SHA-256 is
`dda5f8b5e1ca95ca0b709122d1fa2826ba647e05d720d829b9e06b4b3f88e833`.
The detached checkout is `../blockvideo-d35-candidate`, has detached `HEAD` at that
exact commit, and has empty tracked and ignored status before and after the gate.

The D36 delivery commit is tooling and documentation only. It is not candidate
behavior. The candidate manifest therefore names the D35 commit, while the separate
tool attestation names the later clean tooling `HEAD`. The freezer has no dry-run
interface; the exact candidate ID and canonical artifact hashes are emitted only after
this report is committed and pushed, avoiding circular or stale tool-source identity.

## Candidate gate

The backend gate ran from the detached candidate using the existing tooling-checkout
virtual environment with bytecode, pytest temporary state, Ruff cache, and uv cache
redirected outside the candidate.

1. The first full backend run was not green: **1305 passed, 7 skipped, 1 failed** in
   284.05 s. The existing load-sensitive
   `test_repair_shares_original_deadline` exhausted its 65 ms deadline before its
   second attempt.
2. The exact failed test immediately passed in isolation: **1 passed** in 3.37 s.
   This was diagnostic evidence only.
3. A fresh complete backend rerun passed: **1306 passed, 7 skipped**, one existing
   Starlette/httpx deprecation warning, in 297.49 s.
4. `ruff check .` passed.

The frontend was materialized outside both repositories from
`git archive 522775516c0797abdb313e3432339a3a444b7ae2 frontend`. All **73** tracked
frontend files were byte-equal to the detached checkout before execution; their
canonical path/content aggregate was
`61b54622a28ee3ae7d00f4e8ba2654d0dd49895a78400a326f1f3d014e1ac7d1`.
Dependencies, generated output, and caches remained in the external environment.

5. `pnpm@10.18.3 test` passed: **17 files, 157 tests**.
6. `pnpm@10.18.3 build` passed: **190 modules transformed**.
7. `pnpm@10.18.3 lint` passed.

The build regenerates committed Vite configuration derivatives in its external
materialization, so post-build equality is asserted on the detached candidate itself,
not on generated build-tree copies. Final candidate `git status --porcelain=v1
--untracked-files=all` and `git status --ignored --porcelain=v1` are both empty.

## Freeze and evidence contract

After the tracked D36 commit is pushed, the real freezer runs from that clean tooling
`HEAD` and writes only ignored
`release-evidence/d36/<candidate-id>/`. A complete publication contains exactly:

- `freeze-manifest.json`;
- `d36-tool-attestation.json`;
- `.d36-publication-complete`.

Final validation must recompute the control hash, manifest content aggregate,
candidate ID, commit-derived UTC `created_at`, tool-attestation aggregate, artifact
sizes/hashes, and completion marker. It must also prove the candidate remains clean and
that the tooling checkout differs from `HEAD` only by ignored release evidence.

## Boundary and limits

D36-D40 code is external post-candidate tooling. Candidate `app` modules do not import
it, and the detached candidate is never edited to add it. A candidate behavior change
requires a new candidate and freeze; a tooling-only change changes the tool attestation
and requires evidence regeneration without changing the D35 identity.

No held-out material was read or evaluated. No tag, publication, deployment, release
readiness decision, real provider, user database, or user media was used. D36 supplies
content-addressed reconstruction evidence only.
