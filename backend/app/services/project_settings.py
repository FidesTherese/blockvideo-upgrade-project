"""Shared mutation rules for persisted project settings."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.models.project import Project
from app.services.invalidation import invalidate_project_settings


def apply_project_settings(project: Project, updates: Mapping[str, Any]) -> set[str]:
    """Apply validated settings and invalidate only affected pipeline stages.

    The caller owns commit and rollback. Unknown attributes fail before any
    assignment so a malformed internal caller cannot partially mutate a row.
    """
    unknown = [field for field in updates if not hasattr(project, field)]
    if unknown:
        raise ValueError(f"unknown project settings: {sorted(unknown)}")
    changed = {field for field, value in updates.items() if getattr(project, field) != value}
    for field in changed:
        setattr(project, field, updates[field])
    invalidate_project_settings(project, changed)
    return changed
