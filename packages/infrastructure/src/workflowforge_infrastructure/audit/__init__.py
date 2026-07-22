"""Audit persistence adapters."""

from workflowforge_infrastructure.audit.repository import SqlAlchemyAuditRepository

__all__ = ["SqlAlchemyAuditRepository"]
