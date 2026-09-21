# D23 — One observed local-model configuration

Use the previously user-selected, already downloaded Ternary Bonsai 27B Heretic Ja
Q2_g64 through LM Studio on this PC. Record it as a compressed 27B development
configuration, not a newly selected small-parameter model or release approval.
No model download, cloud service, credentials or automatic model fallback is added.

## Deliverables

- Record the exact installed model file, size, quantization, loaded instance,
  runtime, context, generation parameters, hardware and observed memory/latency.
- Keep model selection in LANGUAGE_MODEL / LANGUAGE_BASE_URL; document switching
  and restart. Add a read-only connection display and explicit connection check in
  the project page so the user can see what interprets natural-language requests.
- A connection check validates the same loopback-only URL, disables environment
  proxies and redirects, caps time/response size, and reads the model list only.
  A listed model is not proof of a completed inference. No project content is sent.
- Add a reproducible synthetic development probe with fixed expected outcomes,
  including D22 compound requests. Record exact candidate counts, prompt/schema
  hashes, actual model responses, token usage when reported, latency and system
  memory snapshots. Separate raw-model correctness from application guard results.
- Exercise real inference through the existing application/receipt path in isolated
  storage once the user starts the local server. No fixed adapter counts as a real
  model call. Test unavailable/missing model paths and preserve no-fallback behavior.

## Observed problems and authorized extension

The user started LM Studio and independently confirmed context 8192 on this turn.
Real probes found ungrounded subtitle amounts and dropped pending values. The user
explicitly authorized fixing accidental saves within D23, preserving immediate
save for supported explicit values. Add a conservative application check before
preparation: bind subtitle values/deltas to supplied quantities (the existing
"少し" = 2 px rule still applies), never to model examples or saved history. If an
answer omits a pending explicit subtitle value, ask before any partial save. Keep
the model's original proposal for audit. This is value validation, not retrieval,
an intent router, or a guarantee of general language understanding.

The user subsequently authorized completing accidental-save fixes in this unit.
Observed unrelated numeric settings and dropped speed requests are also rejected
before preparation. LM Studio answered an absent model ID using the loaded model;
LocalChatAdapter now requires an exact response model identity. No replacement
model or extra repair call is used. See `work-report-23.md` for final results.
The prior server-start denial was not bypassed: the user performed that startup.
Keep D24 held-out evaluation and D26 retrieval separate.

The publisher's model card declares Apache-2.0 and describes research/experimental
use with a recommendation against public end-user services. Record that scope for
this local development run; future release selection remains a separate decision.
Sources: https://huggingface.co/OS-Software/Ternary-Bonsai-27B-heretic-ja-GGUF,
https://lmstudio.ai/docs/developer/core/server,
https://lmstudio.ai/docs/developer/openai-compat/structured-output.
