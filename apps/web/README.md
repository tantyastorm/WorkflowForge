# Web App

Belongs here: the React frontend for operators, workflow authors, reviewers, and administrators.

Does not belong here: backend business rules, API implementation, worker execution code, scheduler logic, or backend infrastructure adapters.

Owner: `apps/web` frontend process and user interface workspace.

Dependency direction: communicates with backend APIs through stable contracts. It must not import backend Python packages or duplicate backend business rules.

## Frontend Foundation

The web app uses React, TypeScript, Vite, React Router, TanStack Query, Zod, native `fetch`, Vitest, Testing Library, ESLint, Prettier, and pnpm.

Install dependencies:

```powershell
corepack pnpm --dir apps/web install
```

Run the development server:

```powershell
corepack pnpm --dir apps/web dev --host 127.0.0.1
```

Open:

```text
http://127.0.0.1:5173
```

Public health remains available at:

```text
http://127.0.0.1:5173/status
```

Authenticated operators use:

```text
http://127.0.0.1:5173/login
http://127.0.0.1:5173/app/system
http://127.0.0.1:5173/app/tenant-context
http://127.0.0.1:5173/app/documents
http://127.0.0.1:5173/app/batches
http://127.0.0.1:5173/app/cases
```

Quality commands:

```powershell
corepack pnpm --dir apps/web format:check
corepack pnpm --dir apps/web lint
corepack pnpm --dir apps/web typecheck
corepack pnpm --dir apps/web test:run
corepack pnpm --dir apps/web build
```

Use `corepack pnpm --dir apps/web format` to apply Prettier formatting.

## Environment

Copy `apps/web/.env.example` to an untracked local `.env` if needed:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_CSRF_COOKIE_NAME=workflowforge_csrf
VITE_CSRF_HEADER_NAME=X-CSRF-Token
```

The API base URL is parsed with Zod, must be an absolute HTTP or HTTPS URL, and is normalized without trailing slashes. CSRF names must match the backend auth settings. Do not put backend secrets, database URLs, Redis URLs, object-storage credentials, API keys, access tokens, or refresh tokens in Vite environment variables.

## Authentication

The React auth foundation uses the backend Phase 2 session endpoints:

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/logout-all`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/organizations`
- `GET /api/v1/organizations/{organization_id}/tenancy/context`

The access token is kept in memory only. The refresh token stays in the backend-issued HttpOnly cookie and is never read by React. Refresh, logout, and logout-all requests include credentials and copy the readable CSRF cookie into the configured CSRF header. The selected organization ID may be stored in localStorage, but it is revalidated through the current user's organization list and tenant-context endpoint during session restoration.

## System Status

`/status` displays live platform health from the backend health endpoints:

- `GET /health/live`
- `GET /health/ready`
- `GET /health/dependencies`

The page shows API liveness, API readiness, PostgreSQL, Redis, object storage, worker, and scheduler status. Dependency health refreshes automatically every 20 seconds through TanStack Query and can also be refreshed manually with the page refresh button. A dependency `503` response is parsed as health data because the backend uses it to report degraded dependencies.

Run the backend and frontend together from the repository root:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

Then open `http://127.0.0.1:5173/status`. Local frontend env overrides belong in untracked Vite env files.

## Current Scope

The app currently provides a neutral operator shell, provider composition, typed environment parsing, an API-client foundation, session restoration, login/logout/logout-all, current-user organization selection, permission-aware route guards, loading/error components, an error boundary, the operational system-status page, tenant-context diagnostics, and Phase 3 document, batch, and case pages. It does not include public registration, password reset, membership administration, organization creation, workflow execution screens, review/approval flows, charts, generated API clients, or final UI branding.
