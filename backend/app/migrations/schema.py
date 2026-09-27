"""SQLite v0-to-v1 classification, additive DDL, and identity validation."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from typing import Literal, TypeAlias

from sqlalchemy import MetaData, create_engine
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateColumn, CreateIndex, CreateTable

from app.migrations.contracts import MigrationError, TableIdentity


SQLiteAffinity: TypeAlias = Literal["INTEGER", "TEXT", "BLOB", "REAL", "NUMERIC"]

CRITICAL_TABLES = (
    "projects",
    "blocks",
    "generation_jobs",
    "operation_requests",
    "external_calls",
    "generation_artifacts",
    "settings_revisions",
    "language_requests",
    "language_turns",
)


def sqlite_affinity(declared_type: str) -> SQLiteAffinity:
    """Derive affinity using SQLite's ordered declared-type rules."""
    normalized = declared_type.upper()
    if "INT" in normalized:
        return "INTEGER"
    if any(token in normalized for token in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if "BLOB" in normalized or not normalized:
        return "BLOB"
    if any(token in normalized for token in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def _quote(identifier: str) -> str:
    return sqlite_dialect().identifier_preparer.quote(identifier)


def _normalized_identifier(identifier: str) -> str:
    return identifier.casefold()


def _identifier_map(identifiers: Iterable[str]) -> dict[str, str]:
    indexed: dict[str, str] = {}
    for identifier in identifiers:
        normalized = _normalized_identifier(identifier)
        if normalized in indexed:
            raise MigrationError("unsupported_legacy_schema")
        indexed[normalized] = identifier
    return indexed


def _validate_metadata_identifiers(metadata: MetaData) -> None:
    _identifier_map(table.name for table in metadata.tables.values())
    for table in metadata.tables.values():
        _identifier_map(column.name for column in table.columns)


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _table_name_map(connection: sqlite3.Connection) -> dict[str, str]:
    return _identifier_map(_table_names(connection))


def _table_info(
    connection: sqlite3.Connection, table: str
) -> dict[str, tuple[str, int]]:
    info = {
        str(row[1]): (str(row[2] or ""), int(row[5]))
        for row in connection.execute(f"PRAGMA table_info({_quote(table)})")
    }
    _identifier_map(info)
    return info


def _scratch_schema(metadata: MetaData) -> dict[str, dict[str, tuple[str, int]]]:
    _validate_metadata_identifiers(metadata)
    scratch = sqlite3.connect(":memory:")
    engine = create_engine(
        "sqlite://",
        creator=lambda: scratch,
        poolclass=StaticPool,
    )
    try:
        metadata.create_all(engine)
        return {
            table: _table_info(scratch, table)
            for table in _table_names(scratch)
        }
    except MigrationError:
        raise
    except Exception as exc:
        raise MigrationError("unsupported_legacy_schema") from exc
    finally:
        engine.dispose()


def classify_v0(connection: sqlite3.Connection, metadata: MetaData) -> None:
    """Reject known table/column collisions with unequal SQLite affinity."""
    expected = _scratch_schema(metadata)
    expected_tables = _identifier_map(expected)
    observed_tables = _table_name_map(connection)
    for normalized_table in observed_tables.keys() & expected_tables.keys():
        observed_columns = _table_info(
            connection, observed_tables[normalized_table]
        )
        expected_columns = expected[expected_tables[normalized_table]]
        observed_names = _identifier_map(observed_columns)
        expected_names = _identifier_map(expected_columns)
        for normalized_column in observed_names.keys() & expected_names.keys():
            observed = observed_columns[observed_names[normalized_column]]
            current = expected_columns[expected_names[normalized_column]]
            if sqlite_affinity(observed[0]) != sqlite_affinity(current[0]):
                raise MigrationError("unsupported_legacy_schema")


def _missing_columns(
    connection: sqlite3.Connection, metadata: MetaData
) -> list[tuple[str, object]]:
    existing_tables = _table_name_map(connection)
    missing: list[tuple[str, object]] = []
    for table in metadata.sorted_tables:
        actual_table = existing_tables.get(_normalized_identifier(table.name))
        if actual_table is None:
            continue
        present = _identifier_map(_table_info(connection, actual_table))
        for column in table.columns:
            if _normalized_identifier(column.name) in present:
                continue
            if not column.nullable and column.server_default is None:
                raise MigrationError("unsupported_legacy_schema")
            missing.append((actual_table, column))
    return missing


def _create_missing_tables(
    connection: sqlite3.Connection,
    metadata: MetaData,
    existing_tables: dict[str, str],
) -> None:
    dialect = sqlite_dialect()
    for table in metadata.sorted_tables:
        if _normalized_identifier(table.name) in existing_tables:
            continue
        connection.execute(str(CreateTable(table).compile(dialect=dialect)))
        for index in sorted(table.indexes, key=lambda item: item.name or ""):
            connection.execute(str(CreateIndex(index).compile(dialect=dialect)))


def apply_v0_to_v1(connection: sqlite3.Connection, metadata: MetaData) -> None:
    """Validate and apply only additive current-schema operations."""
    version_row = connection.execute("PRAGMA user_version").fetchone()
    version = int(version_row[0]) if version_row else 0
    if version > 1:
        raise MigrationError("schema_too_new")
    if version < 0:
        raise MigrationError("unsupported_legacy_schema")
    classify_v0(connection, metadata)
    if version == 1:
        return

    missing_columns = _missing_columns(connection, metadata)
    existing_tables = _table_name_map(connection)
    dialect = sqlite_dialect()
    if connection.in_transaction:
        raise MigrationError("migration_failed")
    try:
        connection.execute("BEGIN IMMEDIATE")
        _create_missing_tables(connection, metadata, existing_tables)
        for table_name, column in missing_columns:
            column_ddl = str(CreateColumn(column).compile(dialect=dialect))
            connection.execute(
                f"ALTER TABLE {_quote(table_name)} ADD COLUMN {column_ddl}"
            )
        connection.execute("PRAGMA user_version=1")
        connection.commit()
    except MigrationError:
        connection.rollback()
        raise
    except sqlite3.Error as exc:
        connection.rollback()
        raise MigrationError("migration_failed") from exc


def _typed_primary_key(value: object) -> dict[str, str]:
    if isinstance(value, int) and not isinstance(value, bool):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, str):
        return {"type": "text", "value": value}
    raise MigrationError("migration_verification_failed")


def _identity_digest(
    table: str, primary_key_columns: tuple[str, ...], rows: Iterable[tuple[object, ...]]
) -> str:
    encoded_rows = []
    for row in rows:
        encoded = [_typed_primary_key(value) for value in row]
        encoded_bytes = json.dumps(
            encoded, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        encoded_rows.append((encoded_bytes, encoded))
    encoded_rows.sort(key=lambda item: item[0])
    payload = {
        "primary_key_columns": list(primary_key_columns),
        "rows": [item[1] for item in encoded_rows],
        "table": table,
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _primary_key_columns(
    info: dict[str, tuple[str, int]],
) -> tuple[str, ...]:
    positioned = sorted(
        ((position, column) for column, (_, position) in info.items() if position > 0)
    )
    if not positioned or [position for position, _ in positioned] != list(
        range(1, len(positioned) + 1)
    ):
        raise MigrationError("unsupported_legacy_schema")
    return tuple(column for _, column in positioned)


def critical_identity_snapshot(
    connection: sqlite3.Connection,
    metadata: MetaData,
) -> dict[str, TableIdentity]:
    """Capture identities using exact ordered primary keys from current metadata."""
    expected = _scratch_schema(metadata)
    expected_tables = _identifier_map(expected)
    observed_tables = _table_name_map(connection)
    snapshot: dict[str, TableIdentity] = {}
    for table in CRITICAL_TABLES:
        normalized_table = _normalized_identifier(table)
        expected_table = expected_tables.get(normalized_table)
        if expected_table is None:
            raise MigrationError("unsupported_legacy_schema")
        actual_table = observed_tables.get(normalized_table)
        if actual_table is None:
            continue

        expected_info = expected[expected_table]
        observed_info = _table_info(connection, actual_table)
        expected_primary_key = _primary_key_columns(expected_info)
        observed_primary_key = _primary_key_columns(observed_info)
        if tuple(map(_normalized_identifier, observed_primary_key)) != tuple(
            map(_normalized_identifier, expected_primary_key)
        ):
            raise MigrationError("unsupported_legacy_schema")

        observed_columns = _identifier_map(observed_info)
        try:
            selected_columns = tuple(
                observed_columns[_normalized_identifier(column)]
                for column in expected_primary_key
            )
        except KeyError as exc:
            raise MigrationError("unsupported_legacy_schema") from exc
        quoted_columns = ", ".join(_quote(column) for column in selected_columns)
        try:
            rows = connection.execute(
                f"SELECT {quoted_columns} FROM {_quote(actual_table)}"
            ).fetchall()
            row_count_row = connection.execute(
                f"SELECT COUNT(*) FROM {_quote(actual_table)}"
            ).fetchone()
        except sqlite3.Error as exc:
            raise MigrationError("unsupported_legacy_schema") from exc
        if row_count_row is None:
            raise MigrationError("unsupported_legacy_schema")
        row_count = int(row_count_row[0])
        canonical_primary_key = tuple(expected_primary_key)
        snapshot[table] = TableIdentity(
            table=table,
            row_count=row_count,
            primary_key_columns=canonical_primary_key,
            primary_key_sha256=_identity_digest(
                table, canonical_primary_key, rows
            ),
        )
    return snapshot


def _has_columns(
    schemas: dict[str, set[str]], table: str, columns: set[str]
) -> bool:
    return columns <= schemas.get(table, set())


def _require_no_rows(connection: sqlite3.Connection, query: str) -> None:
    if connection.execute(query).fetchone() is not None:
        raise MigrationError("migration_verification_failed")


def validate_critical_references(connection: sqlite3.Connection) -> None:
    """Validate declared and D34 semantic ownership references when present."""
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise MigrationError("migration_verification_failed")
    schemas = {
        table: set(_table_info(connection, table))
        for table in _table_names(connection)
    }
    checks: list[tuple[set[tuple[str, frozenset[str]]], str]] = [
        (
            {
                ("blocks", frozenset({"project_id"})),
                ("projects", frozenset({"id"})),
            },
            "SELECT 1 FROM blocks b LEFT JOIN projects p ON p.id=b.project_id "
            "WHERE p.id IS NULL LIMIT 1",
        ),
        (
            {
                ("generation_jobs", frozenset({"id", "project_id", "parent_job_id"})),
                ("projects", frozenset({"id"})),
            },
            "SELECT 1 FROM generation_jobs j LEFT JOIN projects p ON p.id=j.project_id "
            "LEFT JOIN generation_jobs parent ON parent.id=j.parent_job_id "
            "WHERE p.id IS NULL OR (j.parent_job_id IS NOT NULL AND "
            "(parent.id IS NULL OR parent.project_id<>j.project_id)) LIMIT 1",
        ),
        (
            {
                ("external_calls", frozenset({"job_id"})),
                ("generation_jobs", frozenset({"id"})),
            },
            "SELECT 1 FROM external_calls c LEFT JOIN generation_jobs j ON j.id=c.job_id "
            "WHERE j.id IS NULL LIMIT 1",
        ),
        (
            {
                ("generation_artifacts", frozenset({"project_id", "job_id"})),
                ("projects", frozenset({"id"})),
                ("generation_jobs", frozenset({"id", "project_id"})),
            },
            "SELECT 1 FROM generation_artifacts a LEFT JOIN projects p ON p.id=a.project_id "
            "LEFT JOIN generation_jobs j ON j.id=a.job_id "
            "WHERE p.id IS NULL OR (a.job_id IS NOT NULL AND "
            "(j.id IS NULL OR j.project_id<>a.project_id)) LIMIT 1",
        ),
        (
            {
                ("settings_revisions", frozenset({"project_id", "revision", "restored_from_revision"})),
                ("projects", frozenset({"id"})),
            },
            "SELECT 1 FROM settings_revisions s LEFT JOIN projects p ON p.id=s.project_id "
            "LEFT JOIN settings_revisions source ON source.project_id=s.project_id "
            "AND source.revision=s.restored_from_revision WHERE p.id IS NULL OR "
            "(s.restored_from_revision IS NOT NULL AND source.id IS NULL) LIMIT 1",
        ),
        (
            {
                ("projects", frozenset({"id", "current_artifact_id"})),
                ("generation_artifacts", frozenset({"id", "project_id"})),
            },
            "SELECT 1 FROM projects p LEFT JOIN generation_artifacts a "
            "ON a.id=p.current_artifact_id WHERE p.current_artifact_id IS NOT NULL "
            "AND (a.id IS NULL OR a.project_id<>p.id) LIMIT 1",
        ),
        (
            {
                ("operation_requests", frozenset({"project_id", "job_id"})),
                ("generation_jobs", frozenset({"id", "project_id"})),
            },
            "SELECT 1 FROM operation_requests r JOIN generation_jobs j ON j.id=r.job_id "
            "WHERE j.project_id<>r.project_id LIMIT 1",
        ),
        (
            {
                ("language_requests", frozenset({"project_id", "core_request_id"})),
                ("operation_requests", frozenset({"request_id", "project_id"})),
            },
            "SELECT 1 FROM language_requests l LEFT JOIN operation_requests r "
            "ON r.request_id=l.core_request_id "
            "WHERE r.request_id IS NOT NULL AND (l.project_id IS NULL "
            "OR r.project_id IS NULL OR r.project_id<>l.project_id) LIMIT 1",
        ),
    ]
    for requirements, query in checks:
        if all(_has_columns(schemas, table, set(columns)) for table, columns in requirements):
            _require_no_rows(connection, query)

    turn_columns = {"request_id", "parent_request_id", "successor_request_id"}
    if _has_columns(schemas, "language_turns", turn_columns) and _has_columns(
        schemas, "language_requests", {"request_id"}
    ):
        _require_no_rows(
            connection,
            "SELECT 1 FROM language_turns t "
            "LEFT JOIN language_requests own ON own.request_id=t.request_id "
            "LEFT JOIN language_requests parent_request "
            "ON parent_request.request_id=t.parent_request_id "
            "LEFT JOIN language_turns parent_turn "
            "ON parent_turn.request_id=t.parent_request_id "
            "LEFT JOIN language_requests successor_request "
            "ON successor_request.request_id=t.successor_request_id "
            "LEFT JOIN language_turns successor_turn "
            "ON successor_turn.request_id=t.successor_request_id "
            "WHERE own.request_id IS NULL OR "
            "(t.parent_request_id IS NOT NULL AND "
            "(parent_request.request_id IS NULL OR parent_turn.request_id IS NULL "
            "OR parent_turn.successor_request_id IS NULL "
            "OR parent_turn.successor_request_id<>t.request_id)) OR "
            "(t.successor_request_id IS NOT NULL AND "
            "(successor_request.request_id IS NULL OR successor_turn.request_id IS NULL "
            "OR successor_turn.parent_request_id IS NULL "
            "OR successor_turn.parent_request_id<>t.request_id)) LIMIT 1",
        )
