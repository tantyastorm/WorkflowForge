# WorkflowForge V1 Scope

This document defines the planned WorkflowForge V1 scope at a high level. It distinguishes V1 capabilities from later possibilities and from the narrower Phase 1 implementation boundary.

V1 scope is planned product scope, not current implemented functionality.

## V1 Capability Groups

### Platform Foundation

V1 includes a modular monolith with separate API, worker, scheduler, and web processes. The backend is planned around a REST API, PostgreSQL for durable state, Redis for coordination and background work, and S3-compatible object storage for documents and artifacts.

The platform foundation includes migrations, configuration, health checks, structured logging, Docker Compose for local development, CI, and tests. These capabilities make the product operable before workflow features become complex.

### Identity and Access

V1 includes owner and operator roles, authentication, authorization, a protected operator console, and basic audit attribution. The goal is to protect workflow operations and record who performed sensitive actions.

The full implementation design is intentionally deferred. This document defines the product need, not the authentication framework or permission model.

### Document Intake and Storage

V1 includes document upload, object storage, document metadata, hashes and deduplication, supported document type tracking, extraction status, source tracking, and version awareness.

Documents are treated as durable workflow inputs. The system should know where a document came from, what version is being processed, and whether extraction has succeeded, failed, or needs retry.

### Extraction and Normalization

V1 includes text extraction, metadata extraction, a normalized document representation, extraction failure tracking, and retryability. Extraction should produce a consistent representation that later workflow steps can consume.

An OCR adapter boundary is expected for future evolution. OCR is not promised in the first implementation slice unless it is explicitly scheduled in a later commit.

### Classification and Routing

V1 includes rule-based classification, AI-assisted classification, confidence and explanations, workflow selection, manual override, and fallback behavior.

Classification should help select the right workflow while keeping uncertainty visible. Low-confidence or conflicting classifications should be reviewable instead of silently routed.

### Workflow Definitions

V1 includes versioned workflow definitions with ordered steps, step configuration, conditions, timeouts, retry policies, human approval steps, deterministic steps, and AI-assisted steps.

Workflow versions used by executions are immutable. Changing a workflow definition should create a new version rather than rewriting the behavior of past executions.

### Execution Engine

V1 includes durable executions, state transitions, step attempts, scheduling, retries, idempotency, timeout handling, cancellation, resume and recovery, partial failure handling, dead-letter handling, and execution history.

The execution engine should make progress explicit. Operators should be able to see which step ran, which attempt failed, what can be retried, and why an execution stopped.

### AI Provider Layer

V1 includes a provider-neutral interface, an OpenAI adapter, a mock provider for deterministic tests, structured outputs, prompt versioning, schema validation, retry on invalid output, token and usage metadata, and deterministic testing through mocks.

An Anthropic adapter may be included in V1 if it is scheduled explicitly; the provider boundary should allow it without reshaping the product. This commit does not add SDKs, dependencies, or implementation details.

### API and External Integrations

V1 includes HTTP API steps, credentials and configuration boundaries, request and response mapping, timeout and retry handling, redacted logs, integration adapters, and webhook boundaries where appropriate.

Integrations should expose enough evidence for operators to understand failures without leaking secrets into logs or audit history.

### Browser Automation

V1 includes a browser automation step type, isolated execution, screenshots or artifacts, timeout and retry handling, clear failure evidence, and a credentials boundary.

Playwright is the expected adapter for browser automation, but Phase 1 does not implement it. WorkflowForge does not promise bypassing access controls, CAPTCHAs, platform protections, or terms of service.

### Human Review and Approval

V1 includes review queues, structured review data, approve, reject, request changes, comments or rationale, reviewer attribution, and resuming execution after approval.

Human review captures inspection and feedback. Approval is the explicit decision that allows a workflow to continue or finalize where configured.

### Results and Versioning

V1 includes structured results, schema validation, snapshots, version comparison, source references, JSON and CSV export, and generated artifacts where supported.

Results should be traceable to the workflow version, execution, source inputs, review decisions, and validation outcomes that produced them.

### Operations Console

V1 includes system health, workflow lists, execution lists, status filters, step details, error details, manual retry, cancellation, review queues, result inspection, version comparison, and audit history.

The console is for operating workflows. It should help operators answer what is running, what failed, what needs review, and what happened previously.

### Observability and Auditability

V1 includes structured logs, execution events, correlation IDs, a metrics foundation, dependency health, worker health, durable audit records, redaction rules, and operational visibility.

Observability should support debugging and operations. Auditability should support review of sensitive workflow decisions and manual actions.

### Evaluation

V1 includes test datasets, expected structured outputs, workflow evaluation runs, comparison between workflow or prompt versions, validation rates, failure categorization, and reproducible mock-provider evaluation.

This is practical workflow evaluation, not a full ML evaluation platform. The focus is whether workflow and prompt changes improve structured outcomes and reduce operational failures.

### Reports and Delivery

V1 includes exporting results as JSON and CSV, downloadable artifacts, delivery to configured external systems, execution summaries, and basic operational reports.

Delivery should be configured and observable so operators can see whether results were exported, downloaded, or sent to an external system.

## Later Possibilities

Later versions may expand connector coverage, add more AI providers, introduce richer workflow authoring interfaces, support additional document extraction adapters, deepen analytics, or add deployment options beyond the local-first V1 path.

These possibilities should not distort V1. The first version should remain focused on reliable operated workflows, clear state, recoverable failures, and understandable local development.

## Explicit V1 Non-Goals

V1 does not include:

- Kubernetes.
- Microservices.
- Multi-region deployment.
- Billing.
- Subscription management.
- Marketplace.
- Arbitrary user-authored code execution.
- General-purpose BPMN implementation.
- Full no-code visual workflow builder.
- Autonomous agents with unrestricted tool use.
- Replacing enterprise document-management systems.
- Replacing full observability platforms.
- Unlimited connector catalogue.
- Mobile applications.
- Real-time collaborative editing.
- Event sourcing unless later proven necessary.
- Custom foundation-model training.

## Phase 1 Boundary

Phase 1 implements only repository and development foundations:

- Product documentation.
- Architecture documentation.
- Repository standards.
- Python and frontend foundations.
- Health endpoints.
- Local infrastructure.
- Worker and scheduler diagnostics.
- Migrations foundation.
- Quality tooling.
- CI.
- One system-status frontend page.

Phase 1 does not implement product workflows or business capabilities. It should not include document processing, workflow execution, AI provider integration, browser automation, human approval flows, reports, authentication beyond scheduled foundation work, or production business behavior.
