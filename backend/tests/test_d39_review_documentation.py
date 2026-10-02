"""Per-key documentation gates with consistent and contradictory metadata."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.scripts.d39_smoke import DOC_KEYS, documentation_checks


@pytest.fixture
def documented(tmp_path: Path) -> Path:
    files = {
        'README.md': 'Audited lane: Python 3.12.12, Node.js 24.11.1, pnpm 10.18.3.\n[setup](backend/.env.example)\n',
        'Makefile': 'demo:\n\tpython -m scripts.plan_c_demo --mode all_tools\n',
        'backend/.env.example': '# synthetic\n',
        'backend/pyproject.toml': '[project]\nname="synthetic"\nversion="1"\nrequires-python=">=3.12"\ndependencies=[]\n',
        'backend/uv.lock': 'requires-python=">=3.12"\npackage=[]\n',
        'frontend/package.json': json.dumps({'packageManager': 'pnpm@10.18.3', 'engines': {'node': '>=24.11.1'}, 'dependencies': {'react': '^18.3.1'}}),
        'frontend/pnpm-lock.yaml': "lockfileVersion: '9.0'\nimporters:\n  .:\n    dependencies:\n      react:\n        specifier: ^18.3.1\n        version: 18.3.1\npackages:\n  react@18.3.1:\n    engines: {node: '>=18'}\n",
        'backend/scripts/plan_c_demo.py': 'def prepare_storage(): pass\ndef exclusive_demo(): pass\ndef demo_settings(): pass\ndef create_demo_app(): pass\ndef main():\n    parser.add_argument("--mode", choices=("all_tools", "stateful"))\n',
        'backend/tests/test_d34_migrations.py': 'def test_restore_database_backup_database_lease_unavailable(): pass\n',
        'backend/tests/test_d35_startup_recovery_api.py': 'def test_safe_retry_external_outcome_unknown_migration_failed(): pass\n',
        'frontend/src/test/recovery-status.test.tsx': '/* synthetic reason/action fixture */',
        'specification.md': 'Automated evidence is not human acceptance.\nReal held-out execution is external.\n',
    }
    for name, value in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='utf-8')
    return tmp_path


def checks(source: Path, **results: bool) -> dict[str, bool]:
    return documentation_checks(source, contracts_passed={'recovery_codes': True, 'migration_restore': True, 'ui_recovery': True} | results)


def test_consistent_successor_documentation_passes_all_six(documented: Path) -> None:
    assert checks(documented) == dict.fromkeys(DOC_KEYS, True)


@pytest.mark.parametrize(('name', 'old', 'new', 'key'), [
    ('README.md', 'backend/.env.example', 'missing.md', 'setup_paths'),
    ('backend/pyproject.toml', '>=3.12', '>=3.14', 'locked_versions'),
    ('frontend/package.json', '^18.3.1', '^19', 'locked_versions'),
    ('frontend/pnpm-lock.yaml', "node: '>=18'", "node: '>=26'", 'locked_versions'),
    ('backend/scripts/plan_c_demo.py', 'def create_demo_app', 'def private_app', 'mode_commands'),
    ('backend/scripts/plan_c_demo.py', '"all_tools", "stateful"', '"all_tools", "other"', 'mode_commands'),
    ('specification.md', 'is not human', 'IS human', 'limitation_boundary'),
    ('specification.md', 'is external', 'is internal', 'limitation_boundary'),
])
def test_documentation_contradictions_fail_one_key(documented: Path, name: str, old: str, new: str, key: str) -> None:
    path = documented / name
    path.write_text(path.read_text(encoding='utf-8').replace(old, new), encoding='utf-8')
    assert checks(documented)[key] is False


@pytest.mark.parametrize(('failed', 'key'), [('recovery_codes', 'recovery_codes'), ('ui_recovery', 'recovery_codes'), ('migration_restore', 'migration_restore')])
def test_actual_contract_failures_are_individual_false_values(documented: Path, failed: str, key: str) -> None:
    result = checks(documented, **{failed: False})
    assert result[key] is False
    assert result['migration_restore' if key == 'recovery_codes' else 'recovery_codes'] is True
