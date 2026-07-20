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

## Current Scope

The app currently provides a neutral route-ready shell, provider composition, typed environment parsing, an API-client foundation, loading/error components, and an error boundary. It does not include authentication, dashboards, workflow screens, document screens, charts, business UI, generated API clients, or the real system-status page. System-status integration is the next frontend commit.
