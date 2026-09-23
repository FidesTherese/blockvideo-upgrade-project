# D31 — Adversarial input and model-output safety

## Goal

Prove that hostile language input and untrusted model output cannot bypass the
registered operation core, confirmations, target binding, or current-state checks.
Fix safety failures across all configured interpretation modes rather than adding
mode-specific wording patches.

## Scope

- Add a development-only adversarial corpus for prompt injection, negation and
  withdrawal, guessed references, malformed/oversized/confusable input, unknown
  operations or versions, invalid arguments, extra fields, and disclosure attempts.
- Correct the known `do not retry job 7` cancellation interpretation safely across
  All Tools and stateful retrieval.
- Ensure API errors and logs expose fixed reason codes rather than raw exception,
  prompt, raw request path, filesystem/private path, secret, source-script, or request
  content. A matched framework route template may remain as bounded log metadata.
- Keep model output proposal-only. Registered callables, application-bound targets,
  revisions, confirmations, dialogue currency, and final readiness remain mandatory.

## Non-goals

No general prompt-injection classifier, cloud moderation service, new operation,
or claim that arbitrary natural language is proven safe.

## Acceptance

Adversarial cases create no unauthorized setting change, job, cancellation, remote
call, or arbitrary dispatch. Known-safe supported requests still work. Deterministic
coverage is followed by a bounded local-model run; model quality and core safety are
reported separately.
