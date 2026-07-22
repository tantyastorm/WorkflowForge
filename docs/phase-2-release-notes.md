# Phase 2 Release Notes

Recommended tag after review, commit, and merge: `v0.2.0-alpha.1`.

## Highlights

- Added users, organizations, memberships, password credentials, sessions,
  refresh-token lineage, and security audit persistence.
- Added password authentication with Argon2id, short-lived HS256 access JWTs,
  rotating opaque refresh tokens, logout, logout-all, and durable session checks.
- Added first-owner bootstrap with a PostgreSQL advisory lock and no default
  admin credentials.
- Added organization-scoped tenant context resolution from route parameters.
- Added code-defined roles and permissions with centralized authorization
  policies.
- Added Redis-backed login and refresh rate limiting.
- Added append-only security audit events for bootstrap, authentication,
  sessions, tenant denials, permission denials, and rate limits.
- Added bounded cleanup for expired refresh tokens and old inactive sessions.
- Added the React operator authentication shell with login, session restore,
  organization selection, tenant validation, logout, and protected routes.
- Added CI coverage for backend quality/integration, frontend quality/build, and
  Docker Compose/backend image validation.

## Migrations

Phase 2 includes these migrations:

- `0003_identity_core`
- `0004_memberships`
- `0005_password_credentials`
- `0006_sessions`
- `0007_security_audit_events`

Validated migration paths:

- Empty database to head through Compose migrate service.
- Downgrade from `0007_security_audit_events` to `0006_sessions`.
- Upgrade from `0006_sessions` back to head.
- Full integration migration suite: 36 database integration tests passed.

Known drift:

- `uv run alembic check` reports pre-existing metadata drift for unique-index
  metadata on `documents.content_hash`, `organizations.slug`, and
  `users.normalized_email`, plus the `security_audit_events.metadata` server
  default. This is documented in `docs/security.md` and should be fixed in a
  dedicated migration-maintenance change.

## Configuration

New or security-relevant environment settings are documented in `.env.example`:

- `WORKFLOWFORGE_AUTH_*`
- `WORKFLOWFORGE_BOOTSTRAP_OWNER_PASSWORD`
- `WORKFLOWFORGE_RATE_LIMIT_*`
- `WORKFLOWFORGE_CLEANUP_*`
- `VITE_API_BASE_URL`
- `VITE_CSRF_COOKIE_NAME`
- `VITE_CSRF_HEADER_NAME`

Production requirements:

- Use a non-default JWT signing secret.
- Disable debug mode.
- Set Secure refresh cookies.
- Configure PostgreSQL and Redis passwords.
- Use fail-closed rate limiting.
- Keep access-token lifetime at or below one hour.
- Keep session lifetime at or below 90 days.

## Upgrade Notes

1. Apply migrations to head before starting application services.
2. Run `workflowforge-bootstrap-owner` once on an empty identity store.
3. Configure the web app with the public API base URL and CSRF cookie/header
   names.
4. Verify `/health/live`, `/health/ready`, `/health/dependencies`, and the
   operator login flow.

## Rollback Notes

For local/demo rollback, stop services and restore a database snapshot taken
before Phase 2 migrations. The migrations include downgrade paths for local
validation, but production rollback should prefer snapshot restore because user,
session, and audit data are security records.

## Deferred Work

Still outside Phase 2:

- Public registration, invitation acceptance, password reset, email
  verification, MFA, membership administration, and organization administration.
- Audit dashboards, SIEM export, alerting, retention jobs, partitioning, and
  archival.
- PostgreSQL row-level security.
- Document upload, document tenancy migration, workflow execution, AI providers,
  browser automation, and other Phase 3+ product behavior.

## Validation Summary

- Backend static and type checks passed.
- Backend non-integration tests: 446 passed.
- Backend architecture tests: 9 passed.
- Backend integration tests: 46 passed across database, API, Redis, health, and
  worker/scheduler task suites.
- Frontend format, lint, typecheck, Vitest, and production build passed.
- Clean isolated Compose rebuild, migration service, health endpoints, web
  service, bootstrap, login, refresh, tenant context, logout, and audit proof
  passed.
