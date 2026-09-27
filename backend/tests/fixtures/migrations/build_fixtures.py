"""Deterministic synthetic SQLite ancestry fixtures for D34 migration tests."""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import MetaData, create_engine


FixtureBuilder = Callable[[Path, MetaData], None]


_REMOVED_UPSTREAM_COLUMNS = {
    "projects": (
        "revision",
        "visual_focus_enabled",
        "subtitle_mode",
        "narration_pacing_mode",
        "pronunciation_overrides",
        "current_artifact_id",
    ),
    "generation_jobs": (
        "kind",
        "block_index",
        "input_revision",
        "input_snapshot",
        "input_fingerprint",
        "plan_json",
        "parent_job_id",
        "recovery_message",
    ),
}

_PLAN_C_TABLES = (
    "external_calls",
    "generation_artifacts",
    "language_turns",
    "language_requests",
    "operation_requests",
    "settings_revisions",
    "project_identities",
)


def _create_current(path: Path, metadata: MetaData, *, version: int) -> None:
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(f"PRAGMA user_version={version}")
    finally:
        engine.dispose()


def _seed_project(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO projects (
            id, revision, title, source_script, status, progress,
            llm_provider, image_provider, voicevox_url, voicevox_speaker_id,
            voicevox_speed_scale, voicevox_pitch_scale,
            voicevox_intonation_scale, voicevox_volume_scale,
            subtitle_enabled, subtitle_font_size, subtitle_position,
            subtitle_text_color, subtitle_outline_color, subtitle_background,
            subtitle_max_chars_per_line, visual_focus_enabled, subtitle_mode,
            narration_pacing_mode, pronunciation_overrides,
            narration_sentence_pause_seconds, max_slides_per_block,
            pre_margin_seconds, post_margin_seconds, min_display_seconds,
            use_fake_providers, created_at, updated_at
        ) VALUES (
            101, 1, 'fixture-project', 'fixture-script', 'pending', 0.0,
            'openai_compatible', 'openai', 'http://127.0.0.1:50021', 1,
            1.0, 0.0, 1.0, 1.0,
            1, 48, 'bottom', '#FFFFFF', '#000000', 1,
            36, 0, 'packed', 'fixed', '[]',
            1.5, 1, 0.15, 1.5, 2.0,
            1, '2026-01-02 03:04:05', '2026-01-02 03:04:05'
        )
        """
    )


def build_empty_v0(path: Path, metadata: MetaData) -> None:
    del metadata
    sqlite3.connect(path).close()


def build_upstream_v0(path: Path, metadata: MetaData) -> None:
    _create_current(path, metadata, version=0)
    with sqlite3.connect(path) as connection:
        _seed_project(connection)
        for table in _PLAN_C_TABLES:
            connection.execute(f'DROP TABLE "{table}"')
        for table, columns in _REMOVED_UPSTREAM_COLUMNS.items():
            for column in columns:
                connection.execute(f'ALTER TABLE "{table}" DROP COLUMN "{column}"')
        connection.execute('ALTER TABLE projects ADD COLUMN "legacy_marker" TEXT')
        connection.execute(
            "UPDATE projects SET legacy_marker = 'keep-upstream' WHERE id = 101"
        )
        connection.execute(
            "CREATE TABLE legacy_notes (id INTEGER PRIMARY KEY, note TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO legacy_notes VALUES (1, 'keep-table')")


def build_d30_v0(path: Path, metadata: MetaData) -> None:
    _create_current(path, metadata, version=0)
    with sqlite3.connect(path) as connection:
        _seed_project(connection)


def build_partially_additive_v0(path: Path, metadata: MetaData) -> None:
    _create_current(path, metadata, version=0)
    with sqlite3.connect(path) as connection:
        _seed_project(connection)
        connection.execute("DROP TABLE language_turns")
        connection.execute('ALTER TABLE projects DROP COLUMN "current_artifact_id"')
        connection.execute('ALTER TABLE projects ADD COLUMN "partial_extra" TEXT')
        connection.execute(
            "UPDATE projects SET partial_extra = 'keep-partial' WHERE id = 101"
        )


def build_current_v1(path: Path, metadata: MetaData) -> None:
    _create_current(path, metadata, version=1)
    with sqlite3.connect(path) as connection:
        _seed_project(connection)


def build_newer_v2(path: Path, metadata: MetaData) -> None:
    _create_current(path, metadata, version=2)
    with sqlite3.connect(path) as connection:
        _seed_project(connection)


def build_affinity_collision(
    path: Path,
    metadata: MetaData,
    *,
    table: str,
    column: str,
    declared_type: str,
    value_sql: str,
) -> None:
    del metadata
    with sqlite3.connect(path) as connection:
        connection.execute(
            f'CREATE TABLE "{table}" ("{column}" {declared_type})'
        )
        connection.execute(
            f'INSERT INTO "{table}" ("{column}") VALUES ({value_sql})'
        )


def build_matching_affinity_aliases(path: Path, metadata: MetaData) -> None:
    del metadata
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE projects (
                id INT8,
                title CLOB,
                progress DOUBLE PRECISION,
                subtitle_enabled BOOLEAN
            )
            """
        )
        connection.execute(
            "INSERT INTO projects VALUES (101, 'alias', 1.5, 1)"
        )
        connection.execute("CREATE TABLE external_calls (response_body)")
        connection.execute("INSERT INTO external_calls VALUES (x'31')")


FIXTURE_BUILDERS: dict[str, FixtureBuilder] = {
    "empty_v0": build_empty_v0,
    "upstream_v0": build_upstream_v0,
    "d30_v0": build_d30_v0,
    "partially_additive_v0": build_partially_additive_v0,
    "current_v1": build_current_v1,
    "newer_v2": build_newer_v2,
}


def build_fixture(name: str, path: Path, metadata: MetaData) -> Path:
    """Build one named fixture at a caller-owned empty path."""
    FIXTURE_BUILDERS[name](path, metadata)
    return path
