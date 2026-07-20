# Product Definition

WorkflowForge is an open-source operations platform for building, evaluating, and running reliable AI-assisted workflows across documents, APIs, browser automation, human approvals, and external systems.

This document defines the planned WorkflowForge V1 product direction. It describes intended product behavior, not functionality currently implemented in Phase 1.

## Product Summary

WorkflowForge helps technical teams define and operate business workflows that combine deterministic software steps with AI-assisted steps. A workflow can receive input, process documents, call APIs, run browser automation, validate structured outputs, pause for human review, recover from failures, and produce versioned results.

WorkflowForge is not a chatbot, a prompt playground, a collection of disconnected automation scripts, a generic no-code toy, or an AI wrapper that hides failures. It is intended to make workflow state, retries, errors, validation, review, and audit history explicit.

The product is built for situations where AI can help with ambiguous inputs, but the surrounding operation still needs engineering discipline: durable state, reproducible behavior, validated outputs, safe retries, and operator control.

## Problem Statement

Many teams can build a script that works once. The harder problem is operating that automation when inputs are messy, dependencies fail, and people need to understand what happened.

WorkflowForge addresses practical operational problems:

- AI output can be inconsistent, incomplete, or invalid.
- Long-running workflows may fail after some steps already succeeded.
- Business processes often require retries, recovery, and manual intervention.
- Documents and external systems provide unreliable or changing inputs.
- Human approval is required for sensitive, ambiguous, or high-impact actions.
- Teams need traceability, reproducibility, and clear execution history.
- Scripts are difficult to operate safely at scale.
- Workflow state must survive process restarts.
- Operators need to understand what happened, why it happened, and what can be retried.
- External APIs and browser automations can fail independently from the main application.

The goal is not to remove uncertainty from AI-assisted work. The goal is to make uncertainty visible, bounded, recoverable, and reviewable.

## Target Users

Backend and automation engineers use WorkflowForge to replace fragile scripts with workflows that have durable state, retry behavior, validation, and operational visibility.

AI engineers use it to connect prompts and structured outputs to real workflow execution, evaluation, and failure handling instead of isolated experiments.

Operations teams use it to monitor workflow runs, review exceptions, retry failed steps, and understand execution history without reading logs for every case.

Internal tooling teams use it as a foundation for workflow systems that need APIs, background processing, scheduled jobs, approvals, and admin surfaces.

Agencies building client automations use it to deliver workflows that can be observed, recovered, and handed over with clearer operational expectations.

Technical founders use it to move from prototypes to production-relevant workflow operations without starting with a distributed microservice architecture.

Compliance-sensitive teams use it to keep human control, audit attribution, result versioning, and traceability visible in AI-assisted processes.

Developers replacing fragile scripts use it to keep the flexibility of automation while gaining structure around state, errors, retries, and review.

V1 is not intended to serve every enterprise department or replace broad enterprise platforms. It is focused on technical teams operating AI-assisted workflows.

## Product Principles

Reliability before novelty. WorkflowForge should prefer understandable, recoverable execution over impressive behavior that cannot be operated safely.

Explicit state over hidden behavior. Workflow definitions, executions, steps, attempts, reviews, results, and audit events should be visible product concepts.

PostgreSQL as the durable source of truth. Durable workflow state should live in PostgreSQL so executions can survive process restarts and be inspected later.

Observable execution. Operators should be able to see workflow status, step progress, failures, retries, review decisions, and dependency health.

Structured and validated outputs. AI-assisted steps should produce schema-bound outputs where possible, and invalid outputs should be handled explicitly.

Safe retries and idempotency. Retrying a step should be intentional, traceable, and designed to avoid duplicate side effects where possible.

Human control where automation confidence is insufficient. V1 should support review and approval checkpoints instead of pretending every workflow can run unattended.

Provider and integration boundaries. AI providers and external systems should be accessed through clear adapters so the product is not tied to one vendor or connector.

Recoverable partial failures. A workflow that fails midway should leave enough state to inspect, retry, cancel, or recover.

Local-first development. A new developer should be able to run and understand the system locally as the implementation is introduced.

Production-relevant architecture. The system should use patterns that matter in production, including durable state, health checks, migrations, logs, and tests.

Modular evolution without premature microservices. V1 should remain a modular monolith with separate processes where useful, while avoiding distributed complexity before it is justified.

## Product Lifecycle

A planned V1 workflow follows this general lifecycle:

```text
Input received
-> validated
-> workflow selected
-> execution created
-> steps scheduled
-> deterministic and AI-assisted processing
-> structured output validation
-> retries or recovery when required
-> human review where configured
-> approval or rejection
-> versioned result
-> export or delivery
-> complete audit trail
```

Phase 1 does not implement this lifecycle. Phase 1 documents the product direction and establishes the foundations needed for later implementation commits.

## Major Demo Scenarios

The V1 demo scenarios are intended to prove that WorkflowForge can operate practical AI-assisted workflows end to end. They should remain small enough to understand, but realistic enough to exercise documents, validation, retries, review, and exports.

### Invoice Processing

```text
Invoice upload
-> extraction
-> document classification
-> supplier and invoice data extraction
-> schema validation
-> duplicate check
-> human review when required
-> approval
-> structured export
```

This scenario demonstrates document intake, extraction, classification, duplicate detection, human approval, and structured export.

### Resume Processing

```text
Resume upload
-> extraction
-> candidate data normalization
-> role-specific evaluation
-> structured scoring
-> reviewer approval
-> versioned result
-> export
```

This scenario supports recruiting workflow review, not autonomous hiring decisions. Human review remains explicit, and structured scoring is treated as decision support.

### Contract Review

```text
Contract upload
-> extraction
-> contract classification
-> clause identification
-> risk flagging
-> structured findings
-> human review
-> approved report
```

This scenario demonstrates workflow support for contract review. It is not legal advice and does not replace professional legal judgment.

### API-Enriched Document Workflow

```text
Document intake
-> extraction
-> identifier detection
-> external API lookup
-> data reconciliation
-> exception handling
-> human review
-> delivery
```

This scenario demonstrates external API calls, reconciliation, exceptions, and delivery from a document-driven workflow.

### Browser-Assisted Operations Workflow

```text
Structured input
-> browser session
-> data collection or form interaction
-> screenshot evidence
-> output validation
-> retry or review
-> result storage
```

This scenario demonstrates browser automation with evidence and review. WorkflowForge does not promise bypassing access controls, CAPTCHAs, platform protections, or terms of service.

## Success Criteria for V1

V1 is successful when workflows can be created and run reliably, execution state is durable, failures are visible and recoverable, and AI outputs are validated before they are trusted.

Operators should be able to retry or review work, and document, API, and browser steps should be able to participate in one workflow. Results should be versioned, inspectable, and exportable.

The major demo scenarios should run end to end. A new developer should be able to understand the system from the repository structure and documentation, and local setup should remain straightforward as runtime foundations are added.
