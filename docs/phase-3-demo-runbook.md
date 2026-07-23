# Phase 3 Demo Runbook

This runbook demonstrates the Phase 3 document, batch, and case foundation.

## Start

```powershell
Copy-Item .env.example .env
docker compose up --build -d
uv run alembic upgrade head
```

Create a local owner if the database is empty:

```powershell
$env:WORKFLOWFORGE_BOOTSTRAP_OWNER_PASSWORD='change-this-demo-password'
uv run workflowforge-bootstrap-owner --email owner@example.com --display-name "Owner" --organization-name "Example" --organization-slug example --password-from-env
Remove-Item Env:\WORKFLOWFORGE_BOOTSTRAP_OWNER_PASSWORD
```

Open `http://127.0.0.1:5173/login` and sign in.

## Document Intake

1. Open `http://127.0.0.1:5173/app/documents`.
2. Upload a small PDF, image, or text file.
3. Confirm the document appears in the active list with media type, storage state, byte size, and updated time.
4. Select the document and use Download to open the signed URL in a new tab.
5. Archive the document and confirm it leaves the active list.

## Batches

1. Open `http://127.0.0.1:5173/app/batches`.
2. Create a batch.
3. Select the batch, choose an active document, and add it to the batch.
4. Confirm the membership appears in the detail panel.
5. Archive the batch and confirm it leaves the active list.

## Cases

1. Open `http://127.0.0.1:5173/app/cases`.
2. Create a case with normal, high, low, or urgent priority.
3. Select the case and add an active document.
4. Add a comment, task, and decision.
5. Close and reopen the case.
6. Archive the case and confirm it leaves the active list.

## Out Of Scope

Do not demonstrate OCR, AI classification, extraction, workflow routing, review queues, or approvals as Phase 3 features.
