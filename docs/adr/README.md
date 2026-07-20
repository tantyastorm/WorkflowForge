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
