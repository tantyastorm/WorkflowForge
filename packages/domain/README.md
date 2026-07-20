# Domain Package

Belongs here: core WorkflowForge business concepts, invariants, policies, and pure domain behavior.

Does not belong here: framework code, database access, queues, HTTP clients, browser automation clients, AI provider SDKs, or process startup code.

Owner: inner domain layer.

Dependency direction: must remain independent of application frameworks and infrastructure. It may use stable contracts only when those contracts are domain-neutral.

Python workspace distribution: `workflowforge-domain`.

## Documents

The document domain foundation defines metadata for future uploaded documents without depending on FastAPI, SQLAlchemy, S3, Celery, or AI providers.

Current concepts:

- `DocumentId`: strongly typed UUID identifier.
- `ContentHash`: validated lowercase SHA-256 hex digest.
- `StorageObjectKey`: deterministic, path-safe metadata key derived from the content hash.
- `DocumentStatus`: `registered`, `stored`, and `failed`.
- `Document`: immutable metadata aggregate with original filename, media type, byte size, content hash, object key, lifecycle status, and timestamps.

The current storage key format is `documents/sha256/<first-two-hex>/<next-two-hex>/<sha256>`. The original filename is kept only as a normalized user-facing display value and is not used as the object key.
