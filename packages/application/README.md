# Application Package

Belongs here: use cases, orchestration, ports, command handling, workflow coordination, and application-level policies.

Does not belong here: framework entry points, database implementations, external service clients, frontend code, or provider-specific adapters.

Owner: application layer.

Dependency direction: may depend on `packages/domain` and `packages/contracts`. It must not depend directly on `packages/infrastructure`.

Python workspace distribution: `workflowforge-application`.

## Document Services

The document application foundation defines a `DocumentRepository` port and a focused `DocumentService`.

Current use cases:

- Register document metadata.
- Retrieve document metadata by ID.

Registration is idempotent by content hash for the current non-tenant model. Re-registering identical content returns the existing document metadata. Infrastructure still enforces a database uniqueness constraint so concurrent duplicate inserts converge safely.

The application layer does not write file bytes, call object storage, expose HTTP schemas, or depend on SQLAlchemy.
