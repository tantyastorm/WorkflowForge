# Architecture Decision Records

Architecture Decision Records document durable choices that shape WorkflowForge.

Belongs here: concise ADRs covering architecture, dependencies, operational strategy, and cross-cutting trade-offs.

Does not belong here: transient design notes, implementation tickets, runtime code, or general project documentation.

Owner: project architecture and maintainers.

Dependency direction: ADRs document decisions; they do not define importable code or runtime dependencies.

## Naming Convention

ADRs use a zero-padded sequence number and a short kebab-case title:

```text
0001-modular-monolith.md
```

## Status Values

- `Proposed`: under discussion.
- `Accepted`: current project direction.
- `Superseded`: replaced by a newer ADR.
- `Deprecated`: no longer recommended, but not directly replaced.

## Immutability

Accepted ADRs are not silently rewritten. Small clarifications are acceptable, but material architectural changes require a superseding ADR, an explicit status change, and links between the related decisions.

## Records

- [ADR 0001: Adopt a modular monolith with separate runtime processes](0001-modular-monolith.md)
- [ADR 0002: Authentication and session model](0002-authentication-and-session-model.md)
- [ADR 0003: Tenant isolation strategy](0003-tenant-isolation-strategy.md)
- [ADR 0004: Role and permission model](0004-role-and-permission-model.md)
- [ADR 0005: Audit event storage](0005-audit-event-storage.md)
