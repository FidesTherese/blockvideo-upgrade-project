# D16 — Model interpretation boundary

## Scope and dependency direction

D16 adds a read-only interpretation package and a synthetic development probe.
It does not connect natural language to execution (D17) or add the product input
UI (D18). The existing operation API and generation providers remain unchanged.

`scripts.probe_interpretation -> interpretation.service -> interpretation
contracts/candidates/parser + injected adapter`. Candidate validation imports
only `operations.catalog`, `operations.contracts`, and their schema validator.
The interpretation package must not import operation bootstrap/registry/service,
handlers, ORM, database sessions, workers, or generation services.

The adapter takes a bounded request, explicitly offered operation ID/version
pairs, and a fixed allowlist of minimal state. Catalog definitions contribute
only ID/version, description, examples, and argument schema; implementation names
are not sent. No automatic serialization of a project, script, media, provider
configuration, credentials, or history is permitted.

## Output contract

The JSON root contains only `result`. The result is exactly one of:

- `operation`: an offered `operation_id`, exact `operation_version`, and
  catalog-validated `arguments`.
- `clarification`: a question and missing categories (`target`, `arguments`,
  `intent`). No operation is included.
- `unsupported`: a bounded explanation. No operation is included.

The model cannot choose a trusted target, request ID, base revision, execution
flag, handler, or generation flag. An operation proposal is not an executable
request. Successful interpretation reports `executed: false`; it does not assert
readiness, semantic correctness, or successful persistence. D17 must resolve and
check current target/state and explicit intent again through the existing core.

Reject malformed JSON, duplicate keys, non-finite numbers, prose/markdown wrappers,
extra properties, missing values, wrong types, out-of-range arguments, and IDs or
versions not in the offered set. Do not repair, coerce, execute, or retry output.
Freeze candidate definitions before awaiting the response so the validated set
cannot change during a request.

## Transport and development connection

Reuse the installed `httpx` dependency, not an assumed vendor SDK. A separate
adapter protocol permits replacing the model transport without changing the core.
The initial implementation sends JSON Schema via the local LM Studio-compatible
`/v1/chat/completions` endpoint. It requires one completed text response, rejects
tool calls/refusal/truncation, bounds response size and timeout, ignores proxy
environment variables, refuses redirects, and never retries or weakens the schema.
Only literal loopback / localhost endpoints are allowed by this development
adapter. Enabling remote providers is a separately reviewed adapter/config change.
The verified Ternary Bonsai probe explicitly sends `reasoning_effort: "none"`.
Its default thinking mode exhausted all 768 output tokens before returning JSON;
the adapter correctly rejected the incomplete response. This is an explicit
connection setting, not an automatic fallback. The generic adapter omits the
parameter unless configured. JSON Schema and local validation stay mandatory.

The executable probe contains only fixed synthetic requests and fictitious state;
it accepts no user script or project identifier. It prints a stable Japanese
failure message and reason code without raw provider bodies or exception strings.
Product error rendering remains D18 work. The separate connection/test report
records the user's model, data and zero-cost choices and actual probe evidence.

## Verification

Use offline fake transports for adversarial output and network failure tests.
Verify DB/project/revision/settings history/receipts/jobs/artifacts and filesystem
remain unchanged even after a valid mutation or generation proposal. Test adapter
replacement and import boundaries. Then run the repository-wide backend and
frontend commands in AGENTS.md. Probe the approved local model using synthetic
requests and preserve the exact schema and safe results, marking real inference
separately from deterministic tests. Original schedule checkboxes stay untouched.
