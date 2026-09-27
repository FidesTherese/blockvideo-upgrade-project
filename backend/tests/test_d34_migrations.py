"""D34 versioned SQLite migration and historical compatibility tests."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine

from app.migrations.contracts import MigrationError
from app.migrations.lease import acquire_database_lease
from app.migrations.schema import (
    apply_v0_to_v1,
    classify_v0,
    critical_identity_snapshot,
    sqlite_affinity,
    validate_critical_references,
)
from app.db import Base, init_db, register_models, reset_db_for_tests
from tests.fixtures.migrations.build_fixtures import (
    FIXTURE_BUILDERS,
    build_affinity_collision,
    build_altered_legacy_primary_key,
    build_fixture,
    build_matching_affinity_aliases,
)


EXPECTED_TABLES = {
    "blocks",
    "external_calls",
    "generation_artifacts",
    "generation_jobs",
    "language_requests",
    "language_turns",
    "operation_requests",
    "project_identities",
    "projects",
    "settings_revisions",
}

AFFINITY_COLLISIONS = (
    ("projects", "id", "VARCHAR(32)", "101"),
    ("projects", "title", "INT", "'coercible text'"),
    ("external_calls", "response_body", "TEXT", "x'31'"),
    ("projects", "progress", "DECIMAL(8,2)", "1.5"),
    ("projects", "subtitle_enabled", "REAL", "1"),
)


@pytest.fixture(scope="module", autouse=True)
def registered_models() -> None:
    register_models()


@pytest.fixture()
def historical_db(tmp_path: Path, request: pytest.FixtureRequest) -> Path:
    return build_fixture(request.param, tmp_path / f"{request.param}.db", Base.metadata)


def _schema(connection: sqlite3.Connection) -> dict[str, dict[str, str]]:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    return {
        table: {
            row[1]: sqlite_affinity(row[2])
            for row in connection.execute(f'PRAGMA table_info("{table}")')
        }
        for table in tables
    }


def _dump(connection: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(connection.iterdump())


def test_classify_sqlite_affinity_uses_ordered_sqlite_rules() -> None:
    assert sqlite_affinity("UNSIGNED BIG INT") == "INTEGER"
    assert sqlite_affinity("VARCHAR(255)") == "TEXT"
    assert sqlite_affinity("CLOB") == "TEXT"
    assert sqlite_affinity("") == "BLOB"
    assert sqlite_affinity("DOUBLE PRECISION") == "REAL"
    assert sqlite_affinity("FLOAT") == "REAL"
    assert sqlite_affinity("BOOLEAN") == "NUMERIC"
    assert sqlite_affinity("DECIMAL(8,2)") == "NUMERIC"
    assert sqlite_affinity("BLOBBER") == "BLOB"


def test_sqlite_affinity_does_not_unicode_fold_dotless_i_to_ascii_int() -> None:
    declared_type = "\u0131nt"
    with sqlite3.connect(":memory:") as connection:
        storage_class, value = connection.execute(
            f'SELECT typeof(CAST(7.5 AS "{declared_type}")), '
            f'CAST(7.5 AS "{declared_type}")'
        ).fetchone()

    assert (storage_class, value) == ("real", 7.5)
    assert sqlite_affinity(declared_type) == "NUMERIC"


@pytest.mark.parametrize("fixture_name", ("upstream_v0", "d30_v0", "partially_additive_v0"))
def test_classify_supported_v0_uses_scratch_metadata(
    tmp_path: Path, fixture_name: str
) -> None:
    path = build_fixture(fixture_name, tmp_path / f"{fixture_name}.db", Base.metadata)
    with sqlite3.connect(path) as connection:
        classify_v0(connection, Base.metadata)


@pytest.mark.parametrize(
    ("table", "column", "declared_type", "value_sql"), AFFINITY_COLLISIONS
)
def test_classify_rejects_each_known_affinity_name_collision(
    tmp_path: Path,
    table: str,
    column: str,
    declared_type: str,
    value_sql: str,
) -> None:
    path = tmp_path / f"{table}-{column}.db"
    build_affinity_collision(
        path,
        Base.metadata,
        table=table,
        column=column,
        declared_type=declared_type,
        value_sql=value_sql,
    )
    before = path.read_bytes()

    with sqlite3.connect(path) as connection:
        with pytest.raises(MigrationError) as exc_info:
            classify_v0(connection, Base.metadata)

    assert exc_info.value.reason_code == "unsupported_legacy_schema"
    assert path.read_bytes() == before


def test_classify_accepts_declared_type_aliases_with_equal_affinity(tmp_path: Path) -> None:
    path = tmp_path / "affinity-aliases.db"
    build_matching_affinity_aliases(path, Base.metadata)
    with sqlite3.connect(path) as connection:
        classify_v0(connection, Base.metadata)


def test_distinct_unknown_unicode_identifiers_are_preserved(tmp_path: Path) -> None:
    path = build_fixture("d30_v0", tmp_path / "unicode-identifiers.db", Base.metadata)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            'CREATE TABLE "Ä" ("Ö" TEXT);'
            'CREATE TABLE "ä" ("ö" TEXT);'
            'ALTER TABLE projects ADD COLUMN "Ü" TEXT;'
            'ALTER TABLE projects ADD COLUMN "ü" TEXT;'
        )
        classify_v0(connection, Base.metadata)
        apply_v0_to_v1(connection, Base.metadata)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        project_columns = {
            row[1] for row in connection.execute('PRAGMA table_info("projects")')
        }

    assert {"Ä", "ä"} <= tables
    assert {"Ü", "ü"} <= project_columns


def test_case_insensitive_known_identifiers_are_classified_and_extended(
    tmp_path: Path,
) -> None:
    path = build_fixture("d30_v0", tmp_path / "mixed-case.db", Base.metadata)
    with sqlite3.connect(path) as connection:
        connection.execute('ALTER TABLE projects RENAME TO temporary_projects')
        connection.execute('ALTER TABLE temporary_projects RENAME TO "Projects"')
        connection.execute('ALTER TABLE "Projects" RENAME COLUMN id TO temporary_id')
        connection.execute('ALTER TABLE "Projects" RENAME COLUMN temporary_id TO "ID"')
        connection.execute('ALTER TABLE "Projects" DROP COLUMN current_artifact_id')
        connection.execute("UPDATE \"Projects\" SET title='mixed' WHERE \"ID\"=101")
        connection.commit()

        classify_v0(connection, Base.metadata)
        apply_v0_to_v1(connection, Base.metadata)
        project_tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND lower(name)='projects'"
            )
        ]
        columns = {
            row[1].casefold()
            for row in connection.execute('PRAGMA table_info("Projects")')
        }
        assert project_tables == ["Projects"]
        assert {column.name.casefold() for column in Base.metadata.tables["projects"].columns} <= columns
        assert connection.execute('SELECT "ID", "Title" FROM "Projects"').fetchone() == (
            101,
            "mixed",
        )


@pytest.mark.parametrize("duplicate_kind", ("table", "column"))
def test_case_colliding_known_metadata_identifiers_are_rejected_before_ddl(
    duplicate_kind: str,
) -> None:
    metadata = MetaData()
    if duplicate_kind == "table":
        Table("projects", metadata, Column("id", Integer, primary_key=True))
        Table("PROJECTS", metadata, Column("other_id", Integer, primary_key=True))
    else:
        Table(
            "projects",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("ID", Integer),
        )

    with sqlite3.connect(":memory:") as connection:
        with pytest.raises(MigrationError) as exc_info:
            apply_v0_to_v1(connection, metadata)
        assert not _schema(connection)
    assert exc_info.value.reason_code == "unsupported_legacy_schema"


@pytest.mark.parametrize("fixture_name", tuple(FIXTURE_BUILDERS))
def test_schema_version_fixtures_are_deterministic(
    tmp_path: Path, fixture_name: str
) -> None:
    first = build_fixture(fixture_name, tmp_path / "first.db", Base.metadata)
    second = build_fixture(fixture_name, tmp_path / "second.db", Base.metadata)
    with sqlite3.connect(first) as first_connection, sqlite3.connect(second) as second_connection:
        assert _dump(first_connection) == _dump(second_connection)


@pytest.mark.parametrize("fixture_name", ("upstream_v0", "d30_v0"))
def test_historical_fixture_ddl_is_independent_of_current_metadata(
    tmp_path: Path, fixture_name: str
) -> None:
    path = build_fixture(fixture_name, tmp_path / f"{fixture_name}.db", MetaData())
    with sqlite3.connect(path) as connection:
        assert "projects" in _schema(connection)
        assert connection.execute("SELECT title FROM projects WHERE id=101").fetchone() == (
            "fixture-project",
        )


@pytest.mark.parametrize(
    "historical_db",
    ("empty_v0", "upstream_v0", "d30_v0", "partially_additive_v0"),
    indirect=True,
)
def test_additive_v0_to_v1_matches_scratch_schema_and_preserves_unknown_data(
    historical_db: Path,
) -> None:
    scratch = historical_db.with_name("scratch.db")
    engine = create_engine(f"sqlite:///{scratch.as_posix()}")
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()

    with sqlite3.connect(historical_db) as connection:
        before_tables = _schema(connection)
        legacy_rows = (
            connection.execute("SELECT * FROM legacy_notes").fetchall()
            if "legacy_notes" in before_tables
            else None
        )
        apply_v0_to_v1(connection, Base.metadata)
        migrated = _schema(connection)
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)

    with sqlite3.connect(scratch) as connection:
        expected = _schema(connection)

    assert set(expected) <= set(migrated)
    for table, columns in expected.items():
        assert columns.items() <= migrated[table].items()
    for table, columns in before_tables.items():
        assert columns.items() <= migrated[table].items()
    if legacy_rows is not None:
        with sqlite3.connect(historical_db) as connection:
            assert connection.execute("SELECT * FROM legacy_notes").fetchall() == legacy_rows
            assert connection.execute(
                "SELECT legacy_marker FROM projects WHERE id = 101"
            ).fetchone() == ("keep-upstream",)
    if "partial_extra" in before_tables.get("projects", {}):
        with sqlite3.connect(historical_db) as connection:
            assert connection.execute(
                "SELECT partial_extra FROM projects WHERE id = 101"
            ).fetchone() == ("keep-partial",)


def test_schema_version_v1_is_classified_without_mutation(tmp_path: Path) -> None:
    path = build_fixture("current_v1", tmp_path / "current.db", Base.metadata)
    with sqlite3.connect(path) as connection:
        before = _dump(connection)
        apply_v0_to_v1(connection, Base.metadata)
        assert _dump(connection) == before
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)


def test_schema_version_v2_fails_without_mutation(tmp_path: Path) -> None:
    path = build_fixture("newer_v2", tmp_path / "newer.db", Base.metadata)
    before = path.read_bytes()
    with sqlite3.connect(path) as connection:
        with pytest.raises(MigrationError) as exc_info:
            apply_v0_to_v1(connection, Base.metadata)
    assert exc_info.value.reason_code == "schema_too_new"
    assert path.read_bytes() == before


def test_additive_affinity_failure_precedes_ddl(tmp_path: Path) -> None:
    path = tmp_path / "collision.db"
    build_affinity_collision(
        path,
        Base.metadata,
        table="projects",
        column="id",
        declared_type="TEXT",
        value_sql="101",
    )
    with sqlite3.connect(path) as connection:
        before = _dump(connection)
        with pytest.raises(MigrationError) as exc_info:
            apply_v0_to_v1(connection, Base.metadata)
        assert _dump(connection) == before
        assert connection.execute("PRAGMA user_version").fetchone() == (0,)
    assert exc_info.value.reason_code == "unsupported_legacy_schema"


def test_additive_register_models_has_no_database_side_effect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "not-created.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database.as_posix()}")
    table_names = tuple(Base.metadata.tables)
    register_models()
    register_models()
    assert tuple(Base.metadata.tables) == table_names
    assert set(table_names) == EXPECTED_TABLES
    assert not database.exists()


def test_additive_init_db_only_creates_registered_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "init.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database.as_posix()}")
    from app.core import config

    config.reset_settings_cache()
    reset_db_for_tests()
    try:
        init_db()
        with sqlite3.connect(database) as connection:
            assert set(_schema(connection)) == EXPECTED_TABLES
            assert connection.execute("PRAGMA user_version").fetchone() == (0,)
    finally:
        reset_db_for_tests()
        config.reset_settings_cache()


def test_critical_identity_uses_current_metadata_pk_order(tmp_path: Path) -> None:
    path = build_fixture("d30_v0", tmp_path / "identity.db", Base.metadata)
    with sqlite3.connect(path) as connection:
        snapshot = critical_identity_snapshot(connection, Base.metadata)
    assert snapshot["projects"].primary_key_columns == ("id",)


def test_critical_identity_rejects_altered_legacy_primary_key(tmp_path: Path) -> None:
    path = tmp_path / "altered-pk.db"
    build_altered_legacy_primary_key(path, Base.metadata)
    with sqlite3.connect(path) as connection:
        with pytest.raises(MigrationError) as exc_info:
            critical_identity_snapshot(connection, Base.metadata)
    assert exc_info.value.reason_code == "unsupported_legacy_schema"


def test_critical_identity_rejects_missing_expected_primary_key(tmp_path: Path) -> None:
    path = tmp_path / "missing-pk.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE projects (title TEXT PRIMARY KEY)")
        with pytest.raises(MigrationError) as exc_info:
            critical_identity_snapshot(connection, Base.metadata)
    assert exc_info.value.reason_code == "unsupported_legacy_schema"


MIXED_CASE_MALFORMED_REFERENCE_SCHEMAS = (
    (
        'CREATE TABLE "Blocks" ("Project_ID" INTEGER);'
        'CREATE TABLE "Projects" ("ID" INTEGER);'
        'INSERT INTO "Blocks" VALUES (1);',
    ),
    (
        'CREATE TABLE "Generation_Jobs" ('
        '"ID" INTEGER, "Project_ID" INTEGER, "Parent_Job_ID" INTEGER);'
        'CREATE TABLE "Projects" ("ID" INTEGER);'
        'INSERT INTO "Generation_Jobs" VALUES (1, 1, NULL);',
    ),
    (
        'CREATE TABLE "External_Calls" ("Job_ID" INTEGER);'
        'CREATE TABLE "Generation_Jobs" ("ID" INTEGER);'
        'INSERT INTO "External_Calls" VALUES (1);',
    ),
    (
        'CREATE TABLE "Generation_Artifacts" ("Project_ID" INTEGER, "Job_ID" INTEGER);'
        'CREATE TABLE "Projects" ("ID" INTEGER);'
        'CREATE TABLE "Generation_Jobs" ("ID" INTEGER, "Project_ID" INTEGER);'
        'INSERT INTO "Generation_Artifacts" VALUES (1, NULL);',
    ),
    (
        'CREATE TABLE "Settings_Revisions" ('
        '"ID" INTEGER, "Project_ID" INTEGER, "Revision" INTEGER, '
        '"Restored_From_Revision" INTEGER);'
        'CREATE TABLE "Projects" ("ID" INTEGER);'
        'INSERT INTO "Projects" VALUES (1);'
        'INSERT INTO "Settings_Revisions" VALUES (1, 1, 2, 1);',
    ),
    (
        'CREATE TABLE "Projects" ("ID" INTEGER, "Current_Artifact_ID" INTEGER);'
        'CREATE TABLE "Generation_Artifacts" ("ID" INTEGER, "Project_ID" INTEGER);'
        'INSERT INTO "Projects" VALUES (1, 1);'
        'INSERT INTO "Generation_Artifacts" VALUES (1, 2);',
    ),
    (
        'CREATE TABLE "Operation_Requests" ("Project_ID" INTEGER, "Job_ID" INTEGER);'
        'CREATE TABLE "Generation_Jobs" ("ID" INTEGER, "Project_ID" INTEGER);'
        'INSERT INTO "Operation_Requests" VALUES (1, 1);'
        'INSERT INTO "Generation_Jobs" VALUES (1, 2);',
    ),
    (
        'CREATE TABLE "Language_Requests" ('
        '"Request_ID" TEXT, "Project_ID" INTEGER, "Core_Request_ID" TEXT);'
        'CREATE TABLE "Operation_Requests" ("Request_ID" TEXT, "Project_ID" INTEGER);'
        "INSERT INTO \"Language_Requests\" VALUES ('language', 1, 'core');"
        "INSERT INTO \"Operation_Requests\" VALUES ('core', 2);",
    ),
    (
        'CREATE TABLE "Language_Requests" ("Request_ID" TEXT);'
        'CREATE TABLE "Language_Turns" ('
        '"Request_ID" TEXT, "Parent_Request_ID" TEXT, "Successor_Request_ID" TEXT);'
        "INSERT INTO \"Language_Requests\" VALUES ('parent');"
        "INSERT INTO \"Language_Requests\" VALUES ('child');"
        "INSERT INTO \"Language_Turns\" VALUES ('parent', NULL, NULL);"
        "INSERT INTO \"Language_Turns\" VALUES ('child', 'parent', NULL);",
    ),
)


@pytest.mark.parametrize("schema_sql", MIXED_CASE_MALFORMED_REFERENCE_SCHEMAS)
def test_mixed_case_known_identifiers_execute_every_semantic_reference_check(
    schema_sql: tuple[str],
) -> None:
    with sqlite3.connect(":memory:") as connection:
        connection.executescript(schema_sql[0])
        with pytest.raises(MigrationError) as exc_info:
            validate_critical_references(connection)
    assert exc_info.value.reason_code == "migration_verification_failed"


@pytest.mark.parametrize(
    ("language_project_id", "receipt_project_id"),
    ((None, 1), (2, 1), (1, None)),
)
def test_language_request_with_core_receipt_requires_matching_project(
    language_project_id: int | None,
    receipt_project_id: int | None,
) -> None:
    with sqlite3.connect(":memory:") as connection:
        connection.executescript(
            "CREATE TABLE operation_requests (request_id TEXT PRIMARY KEY, project_id INTEGER);"
            "CREATE TABLE language_requests ("
            "request_id TEXT PRIMARY KEY, core_request_id TEXT, project_id INTEGER);"
        )
        connection.execute(
            "INSERT INTO operation_requests VALUES ('core', ?)",
            (receipt_project_id,),
        )
        connection.execute(
            "INSERT INTO language_requests VALUES ('language', 'core', ?)",
            (language_project_id,),
        )
        with pytest.raises(MigrationError) as exc_info:
            validate_critical_references(connection)
    assert exc_info.value.reason_code == "migration_verification_failed"


def test_receipt_with_existing_job_rejects_null_project_owner() -> None:
    with sqlite3.connect(":memory:") as connection:
        connection.executescript(
            "CREATE TABLE operation_requests (project_id INTEGER, job_id INTEGER);"
            "CREATE TABLE generation_jobs (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL);"
            "INSERT INTO operation_requests VALUES (NULL, 1);"
            "INSERT INTO generation_jobs VALUES (1, 1);"
        )
        with pytest.raises(MigrationError) as exc_info:
            validate_critical_references(connection)
    assert exc_info.value.reason_code == "migration_verification_failed"


def test_language_request_may_reference_deleted_project_when_receipt_ownership_matches() -> None:
    with sqlite3.connect(":memory:") as connection:
        connection.executescript(
            "CREATE TABLE operation_requests (request_id TEXT PRIMARY KEY, project_id INTEGER);"
            "CREATE TABLE language_requests ("
            "request_id TEXT PRIMARY KEY, core_request_id TEXT, project_id INTEGER);"
            "INSERT INTO operation_requests VALUES ('core', 1);"
            "INSERT INTO language_requests VALUES ('language', 'core', 1);"
        )
        validate_critical_references(connection)


@pytest.mark.parametrize(
    ("parent_request_id", "successor_request_id"),
    (("parent", None), (None, "successor")),
)
def test_language_turn_reciprocal_link_rejects_null_other_side(
    parent_request_id: str | None, successor_request_id: str | None
) -> None:
    with sqlite3.connect(":memory:") as connection:
        connection.executescript(
            "CREATE TABLE language_requests (request_id TEXT PRIMARY KEY);"
            "CREATE TABLE language_turns (request_id TEXT PRIMARY KEY, "
            "parent_request_id TEXT, successor_request_id TEXT);"
            "INSERT INTO language_requests VALUES ('current');"
            "INSERT INTO language_requests VALUES ('parent');"
            "INSERT INTO language_requests VALUES ('successor');"
            "INSERT INTO language_turns VALUES ('parent', NULL, NULL);"
            "INSERT INTO language_turns VALUES ('successor', NULL, NULL);"
        )
        connection.execute(
            "INSERT INTO language_turns VALUES ('current', ?, ?)",
            (parent_request_id, successor_request_id),
        )
        with pytest.raises(MigrationError) as exc_info:
            validate_critical_references(connection)
    assert exc_info.value.reason_code == "migration_verification_failed"


def test_schema_version_lease_creates_nested_database_parent(tmp_path: Path) -> None:
    database = tmp_path / "nested" / "database" / "lease.db"
    lease = acquire_database_lease(f"sqlite:///{database.as_posix()}")
    try:
        assert database.parent.is_dir()
        assert lease.lock_path.exists()
        assert not database.exists()
    finally:
        lease.release()


def test_schema_version_lease_is_bound_to_one_database_and_release_is_idempotent(
    tmp_path: Path,
) -> None:
    database = tmp_path / "lease.db"
    url = f"sqlite:///{database.as_posix()}"
    lease = acquire_database_lease(url)
    assert lease.lock_path.exists()
    assert not database.exists()
    lease.assert_held_for(url)

    with pytest.raises(MigrationError) as exc_info:
        lease.assert_held_for(f"sqlite:///{(tmp_path / 'other.db').as_posix()}")
    assert exc_info.value.reason_code == "database_lease_unavailable"
    assert not (tmp_path / "other.db").exists()

    lease.release()
    lease.release()
    assert not lease.lock_path.exists()
    with pytest.raises(MigrationError) as released_error:
        lease.assert_held_for(url)
    assert released_error.value.reason_code == "database_lease_unavailable"
