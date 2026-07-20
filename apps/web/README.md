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

The first real feature route is:

```text
http://127.0.0.1:5173/status
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
```

The value is parsed with Zod, must be an absolute HTTP or HTTPS URL, and is normalized without trailing slashes. Do not put backend secrets, database URLs, Redis URLs, object-storage credentials, or API keys in Vite environment variables.

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
corepack pnpm --dir apps/web dev --host 127.0.0.1
```

Then open `http://127.0.0.1:5173/status`. Local frontend env overrides belong in untracked Vite env files.

## Current Scope

The app currently provides a neutral route-ready shell, provider composition, typed environment parsing, an API-client foundation, loading/error components, an error boundary, and the operational system-status page. It does not include authentication, dashboards, workflow screens, document screens, charts, business UI, generated API clients, or final UI branding.
