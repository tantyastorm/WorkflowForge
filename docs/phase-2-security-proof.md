# Phase 2 Security Proof

Validated locally on 2026-07-22 on branch `feature/identity-tenancy-security`.

## Scope

Phase 2 delivers the first production-relevant identity, tenancy, authorization,
security audit, session cleanup, and React operator authentication foundation.
It does not start Phase 3 workflow execution work.

## Acceptance Matrix

| Capability | Implementation | Proof | Status |
| --- | --- | --- | --- |
| Minimal access JWTs | JWTs contain identity/session claims only; tenant, role, permission, email, secret, and refresh material stay server-side | Unit and API integration auth tests; live login smoke | Passed |
| Cookie refresh transport | Refresh token is cookie-only; access token is JSON only; CSRF cookie/header protects refresh/logout/logout-all | Live curl smoke showed no `refresh_token` JSON field, refresh cookie and CSRF cookie present before logout | Passed |
| Durable sessions and rotation | PostgreSQL `auth_sessions` and `refresh_tokens` track revocation, generation, lineage, and replay evidence | `tests/integration/database`, `tests/integration/api` | Passed |
| First-owner bootstrap | CLI creates one owner, organization, membership, password credential, and audit row in one transaction; rerun refuses | Isolated Compose bootstrap created 1 each and second run exited 2 with `bootstrap.refused` | Passed |
| Tenant context | Tenant context resolves from organization route parameter plus durable active membership | `tests/integration/api/test_tenancy_flow.py`; live tenant context smoke | Passed |
| Code-defined roles and permissions | Roles map to reviewed permission enum; JWTs do not carry permission state | Architecture tests and authz unit tests | Passed |
| Security audit trail | Successes audit with owning transaction; failures and denials persist independently when possible | Audit repository, transaction, API integration tests; live audit row query | Passed |
| Redis rate limiting | Login limits by normalized identifier and client; refresh limits by client; keys hash private values | Unit Redis tests and `tests/integration/redis` | Passed |
| Session cleanup | Bounded cleanup task deletes expired token/session records without blocking audit evidence | Cleanup unit tests and database integration test | Passed |
| React operator auth shell | Login, session restore, organization list, tenant probe, logout, logout-all, protected routes | 57 Vitest tests and production build | Passed |
| Local Compose proof | Clean isolated stack rebuild with PostgreSQL, Redis, MinIO, migrate, API, worker, scheduler, web | `docker compose -p workflowforge-step14 --env-file ... up --build -d` | Passed |
| CI readiness | Backend, frontend, and Docker workflows cover format/lint/typecheck/tests/build/Compose image validation | `.github/workflows` audit | Passed |

## Live Demo Evidence

The Step 14 isolated Compose project used alternate host ports so existing local
developer data was not touched.

Observed live service proof:

- `GET /health/live`: `{"status":"ok","service":"api"}`
- `GET /health/ready`: `{"status":"ready","service":"api"}`
- `GET /health/dependencies`: healthy PostgreSQL, Redis, object storage, worker, scheduler
- `GET http://127.0.0.1:15173/`: HTTP 200 from Vite web service
- `uv run alembic current`: `0007_security_audit_events (head)`

Bootstrap proof on a clean database:

- First bootstrap exit: 0
- Second bootstrap exit: 2
- Rows after both attempts: 1 user, 1 organization, 1 membership, 1 password credential, 2 audit events
- Audit events: `bootstrap.owner_created/success` and `bootstrap.refused/denied`

Live auth smoke proof:

- Login status 200
- Access token returned in JSON
- No refresh token returned in JSON
- Refresh cookie present before logout
- CSRF cookie present before logout
- Organization list status 200 with one organization
- Tenant context status 200 with role `owner` and 10 permissions
- Refresh status 200 with a replacement access token
- Logout status 200

## Threat Checklist

| Threat | Phase 2 mitigation | Residual risk / later work |
| --- | --- | --- |
| Stolen browser storage token | Access token kept in React memory; refresh credential in HttpOnly cookie | XSS prevention remains required as UI surface grows |
| Long-lived bearer compromise | Short access lifetime plus durable session revocation | MFA, device management, and risk-based revocation are later work |
| Refresh replay | Rotation lineage detects used/superseded tokens and revokes affected session | Broader anomaly alerting and SIEM export are later work |
| Cross-tenant access | Route tenant context resolved from server-side active membership and permissions | PostgreSQL RLS is deferred until tenant-owned tables stabilize |
| Role tampering | Roles and permissions resolved server-side, not accepted from clients or JWT claims | Membership admin UI/API is later work |
| Credential stuffing | Redis-backed login and refresh rate limiting with hashed private keys | Production must use fail-closed rate limiting |
| Bootstrap backdoor | No public registration or default admin; one-time bootstrap guarded by advisory lock and state checks | Operational secret handling must be production-managed |
| Audit secret leakage | Audit metadata excludes passwords, raw tokens, token digests, cookies, CSRF values, authorization headers, request bodies, and exception reprs | Retention, export, dashboards, and alerting are later work |
| Cleanup data loss | Cleanup deletes bounded expired/inactive session material; audit FKs are nullable | Retention policy tuning is later work |

## Validation Commands

All commands below passed locally unless noted.

```powershell
docker compose -p workflowforge-step14 --env-file $env:TEMP\workflowforge-step14.env config --quiet
docker compose -p workflowforge-step14 --env-file $env:TEMP\workflowforge-step14.env up --build -d
docker compose -p workflowforge-step14 --env-file $env:TEMP\workflowforge-step14.env exec -T api uv run alembic current
docker compose -p workflowforge-step14 --env-file $env:TEMP\workflowforge-step14.env exec -T api sh -lc 'uv run alembic downgrade 0006_sessions && uv run alembic current && uv run alembic upgrade head && uv run alembic current && uv run alembic check'
uv run ruff format --check .
uv run ruff check .
uv run mypy apps packages tests
uv run pytest -m "not integration"
uv run pytest tests/architecture -v
uv run pytest tests/integration/database -v
uv run pytest tests/integration/api -v
uv run pytest tests/integration/redis -v
uv run pytest tests/integration/health -v
uv run pytest tests/integration/tasks -v
corepack pnpm --dir apps/web format:check
corepack pnpm --dir apps/web lint
corepack pnpm --dir apps/web typecheck
corepack pnpm --dir apps/web test:run
corepack pnpm --dir apps/web build
```

Observed counts:

- Ruff format: 190 files already formatted
- Ruff lint: all checks passed
- Mypy: no issues in 179 source files
- Non-integration tests: 446 passed, 46 deselected
- Architecture tests: 9 passed
- Database integration tests: 36 passed
- API integration tests: 5 passed
- Redis integration tests: 1 passed
- Health integration tests: 2 passed
- Worker/scheduler task integration tests: 2 passed
- Frontend tests: 11 files, 57 tests passed
- Frontend build: `dist/index.html`, one CSS asset, one JS asset

`uv run alembic check` still reports the documented pre-existing metadata drift
for unique-index metadata on `documents.content_hash`, `organizations.slug`, and
`users.normalized_email`, plus the `security_audit_events.metadata` server
default. The downgrade/upgrade round trip itself reached `0007_security_audit_events`
successfully.

## Final Position

Phase 2 is release-ready as an alpha security foundation. Recommended release
tag after commit/merge is `v0.2.0-alpha.1`.
