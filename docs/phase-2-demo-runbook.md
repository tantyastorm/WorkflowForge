# Phase 2 Demo Runbook

Use this runbook to demonstrate the Phase 2 identity and security foundation
from a clean local database. The commands below assume PowerShell.

## 1. Prepare Environment

Copy `.env.example` to `.env` for normal local development, then choose demo-safe
secrets. Do not use the values below for production.

For an isolated demo that does not touch existing local ports or Compose volumes,
create a temporary env file outside the repository:

```powershell
$envFile = Join-Path $env:TEMP 'workflowforge-step14.env'
Copy-Item .env.example $envFile
Add-Content $envFile @'
WORKFLOWFORGE_POSTGRES_HOST_PORT=15433
WORKFLOWFORGE_REDIS_HOST_PORT=16380
WORKFLOWFORGE_MINIO_API_HOST_PORT=19010
WORKFLOWFORGE_MINIO_CONSOLE_HOST_PORT=19011
WORKFLOWFORGE_API_HOST_PORT=18100
WORKFLOWFORGE_WEB_HOST_PORT=15173
WORKFLOWFORGE_CORS_ORIGINS=http://localhost:15173,http://127.0.0.1:15173
VITE_API_BASE_URL=http://localhost:18100
POSTGRES_PASSWORD=workflowforge_step14
WORKFLOWFORGE_DATABASE_PASSWORD=workflowforge_step14
WORKFLOWFORGE_AUTH_JWT_SIGNING_SECRET=workflowforge-step14-demo-secret-change-before-production-0001
MINIO_ROOT_PASSWORD=workflowforge_step14_secret
WORKFLOWFORGE_S3_SECRET_KEY=workflowforge_step14_secret
'@
```

## 2. Start A Clean Stack

```powershell
docker compose -p workflowforge-step14 --env-file $envFile down -v --remove-orphans
docker compose -p workflowforge-step14 --env-file $envFile config --quiet
docker compose -p workflowforge-step14 --env-file $envFile up --build -d
docker compose -p workflowforge-step14 --env-file $envFile ps
```

Expected:

- `postgres`, `redis`, `minio`, `api`, `worker`, and `scheduler` are healthy.
- `migrate` exits successfully.
- `web` is running.

## 3. Verify Health And Migration Head

```powershell
Invoke-RestMethod http://127.0.0.1:18100/health/live
Invoke-RestMethod http://127.0.0.1:18100/health/ready
Invoke-RestMethod http://127.0.0.1:18100/health/dependencies
curl.exe -sS -o NUL -w "%{http_code}" http://127.0.0.1:15173/
docker compose -p workflowforge-step14 --env-file $envFile exec -T api uv run alembic current
```

Expected:

- API live and ready return healthy status JSON.
- Dependency health reports PostgreSQL, Redis, object storage, worker, and
  scheduler healthy.
- Web returns HTTP 200.
- Alembic current is `0007_security_audit_events (head)`.

## 4. Bootstrap First Owner

```powershell
docker compose -p workflowforge-step14 --env-file $envFile exec -T `
  -e WORKFLOWFORGE_BOOTSTRAP_OWNER_PASSWORD='DemoOnly-ChangeMe-123456!' `
  api uv run workflowforge-bootstrap-owner `
  --email owner@example.com `
  --display-name 'Demo Owner' `
  --organization-name 'Demo Org' `
  --organization-slug demo-org `
  --password-from-env
```

Run the same command a second time to prove refusal. The first run should exit 0
and the second should exit 2.

Verify database counts:

```powershell
docker compose -p workflowforge-step14 --env-file $envFile exec -T postgres `
  psql -U workflowforge -d workflowforge `
  -c "select 'users' as table_name, count(*) from users union all select 'organizations', count(*) from organizations union all select 'memberships', count(*) from memberships union all select 'password_credentials', count(*) from password_credentials union all select 'security_audit_events', count(*) from security_audit_events order by table_name;"
```

Expected after two attempts: one user, one organization, one membership, one
password credential, and two audit rows.

## 5. Demonstrate Operator Auth

Open the web app:

```powershell
Start-Process http://127.0.0.1:15173/
```

Then sign in with the bootstrapped owner email and password. Demonstrate:

- Login reaches the protected operator shell.
- Organization selection lists the bootstrapped organization.
- Tenant context resolves successfully.
- Logout returns to the login page.

For a scriptable smoke, use `curl.exe` with a temporary cookie jar and keep raw
tokens out of terminal output. Confirm these booleans instead:

- Login returns 200.
- Access token is present in JSON.
- Refresh token is not present in JSON.
- Refresh cookie is present before logout.
- CSRF cookie is present before logout.
- Organization list returns 200.
- Tenant context returns 200 with role `owner`.
- Refresh returns 200.
- Logout returns 200.

## 6. Teardown

```powershell
docker compose -p workflowforge-step14 --env-file $envFile down -v --remove-orphans
Remove-Item $envFile
```

This removes only the isolated `workflowforge-step14` Compose project and its
volumes.
