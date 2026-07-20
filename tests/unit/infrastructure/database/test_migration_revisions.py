"""Alembic revision identifier tests."""

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migration_revision_identifiers_fit_existing_version_column() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))

    revisions = [script.revision for script in scripts.walk_revisions()]

    assert revisions
    assert all(len(revision) <= 32 for revision in revisions)
