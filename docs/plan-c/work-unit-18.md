# D18 — Natural-language input and authoritative result cards

The user requested the next work unit with the same collaborative workflow and
selected an inline panel at the top of project detail. Keep the existing forms,
generation controls and history. Retrieval remains D26–D27; dialogue state is D19.

The panel identifies the selected project, accepts one complete request, and
separates interpretation, saved settings, and generated-video state. Render success
only from a committed operation result. Compute setting differences from recorded
settings revisions and core values, never model prose or stale form values. When
history lags the receipt, show verification pending, not a current-video claim.
Show generation confirmation with target, settings version and generation scope;
only a deliberate click may send confirm_generation. Recheck staleness in the UI
and retain the server's final validation. A queued job is not a finished video.

Persist the exact request ID/body in sessionStorage before sending. Keep submit
and confirmed-execute attempts distinct. Reload performs GET lookup only, never
automatic mutation. Unknown delivery permits an explicit same-ID resend; a new
intent has a new ID. Poll interpreting requests with GET. Fence late responses by
request/action identity and project; an unmounted sender must not overwrite a newer
session. Block mutation while the outcome is uncertain. Storage failure before a
new request stops submission, so reload cannot silently lose its identity.

Missing input, unsupported, blocked, and failure have distinct cards. Editing a
clarification creates a complete new request; do not imply D19 conversational
memory. Offer a link to the existing arbitrary settings-history restore controls.
Use the existing history/job polling for progress, cancellation and failed output.
No original schedule acceptance checkbox or D01–D17 historical report is changed.

Verify duplicate submit/confirm, delayed replies, reload and lost acknowledgement,
stale confirmation, target switches, immutable body replay, and saved-versus-video
display. Use the real local Ternary Bonsai for a browser flow and fake video
providers with actual FFmpeg in an isolated synthetic DB. Capture browser evidence,
run the required repository checks, and document limitations and cleanup.
