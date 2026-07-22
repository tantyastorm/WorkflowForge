"""Audit repository adapter unit tests."""

from workflowforge_infrastructure.audit import SqlAlchemyAuditRepository


def test_audit_repository_exposes_no_update_or_delete_methods() -> None:
    public_methods = {
        name
        for name in dir(SqlAlchemyAuditRepository)
        if not name.startswith("_") and callable(getattr(SqlAlchemyAuditRepository, name))
    }

    assert "record" in public_methods
    assert "update" not in public_methods
    assert "delete" not in public_methods
    assert "save" not in public_methods
