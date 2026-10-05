"""Catalog-wide and per-model-call operation limits.

The catalog may grow well beyond what one prompt can carry; retrieval narrows it
before any model call. Only a single model call is bounded by the prompt limit.
"""
from __future__ import annotations

# Operation versions the catalog, retrieval scope and diagnostics may hold
# (matches the retrieval scope's binding cap).
MAX_CATALOG_OPERATIONS = 256
# Operation versions offered to the model in one interpretation call.
MAX_PROMPT_CANDIDATES = 32
