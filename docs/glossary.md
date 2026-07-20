# Glossary

This glossary defines WorkflowForge terms for V1 planning and implementation.

## Workflow

A configured business process that coordinates inputs, deterministic steps, AI-assisted steps, reviews, integrations, and outputs.

## Workflow Definition

The editable description of a workflow before it is executed. It contains steps, conditions, timeouts, retry policies, and review requirements.

## Workflow Version

An immutable snapshot of a workflow definition used by executions. Updating a workflow definition should create a new version so past executions remain reproducible.

## Execution

A single run of a workflow version against a specific input. An execution has durable state, step history, review decisions, results, and audit events.

Workflow definition and execution are different: the definition describes what should happen, while the execution records what happened in one run.

## Step

One configured unit of work inside a workflow definition, such as extraction, classification, API lookup, browser automation, AI processing, or human review.

## Step Attempt

One try at running a step during an execution. A step may have multiple attempts because of retries, timeouts, invalid AI output, or recoverable dependency failures.

Step and step attempt are different: the step is planned workflow structure, while the attempt is runtime history.

## Task

A schedulable runtime work item handled by a worker or scheduler. A task may execute a workflow step, resume an execution, perform diagnostics, or run maintenance work.

Task and workflow step are different: a step is part of workflow design, while a task is how runtime work is dispatched.

## Worker

The background process responsible for executing queued workflow tasks and recording their outcomes.

## Scheduler

The process responsible for scheduled work, delayed retries, periodic diagnostics, and time-based execution coordination.

## Trigger

An event or condition that starts or resumes an execution, such as document upload, API request, schedule, webhook, manual retry, or approval.

## Input

The data, document, event, or structured payload used to start an execution or feed a step.

## Artifact

A stored file or generated object produced or collected during execution, such as an uploaded document, extracted text file, screenshot, report, or export.

## Document

A user-provided or system-provided file that can be stored, tracked, extracted, classified, and used as workflow input.

## Extraction

The process of reading useful text and metadata from a document so later workflow steps can operate on it.

## Normalized Document

A consistent internal representation of extracted document content, metadata, source information, and extraction status.

## Classification

The process of assigning a document, input, or execution to a category or workflow route, using rules, AI assistance, or manual override.

## Provider

An external AI service or model source used behind a provider-neutral interface, such as OpenAI or another model provider.

## Adapter

Infrastructure code that connects WorkflowForge ports to a concrete external system, provider, storage service, queue, browser tool, or API.

Provider and integration are different: a provider supplies AI model capabilities, while an integration connects to an external business system or service.

## Port

A stable interface defined by an inner layer that describes what the application needs from infrastructure without naming a concrete implementation.

## Integration

A connection to an external business system or API used by a workflow, such as a CRM, accounting API, document system, or webhook endpoint.

## Structured Output

An AI or deterministic step result shaped according to an expected schema so it can be validated, stored, reviewed, and consumed by later steps.

## Schema

The declared structure and validation rules for inputs, structured outputs, review data, events, or results.

## Retry

A deliberate additional attempt after a recoverable failure, timeout, invalid output, or transient dependency issue.

## Idempotency

The property that retrying or repeating an operation does not create duplicate side effects or inconsistent state.

## Dead-Letter

A state or queue for work that cannot continue automatically after retries or recovery options are exhausted.

## Human Review

A workflow pause where an operator inspects structured data, evidence, errors, or proposed outputs before the workflow proceeds.

## Approval

An explicit reviewer decision that accepts a review item and allows the configured workflow path to continue or finalize.

Human review and approval are different: review is the inspection step, while approval is one possible decision from that review.

## Result

The structured business output of an execution, validated and stored for inspection, comparison, export, or delivery.

## Result Version

A stored snapshot of a result at a point in time, allowing changes after review, correction, or rerun to be compared.

Result and artifact are different: a result is structured business output, while an artifact is a stored file or generated object.

## Audit Event

A durable record of a meaningful workflow, operator, system, or security action.

## Operator

A user who monitors executions, reviews exceptions, retries work, approves or rejects review items, and inspects results.

## Owner

A user with responsibility for configuring workflows, managing access, and overseeing operational settings.

## Dependency Health

The observed availability or status of a required external dependency such as PostgreSQL, Redis, object storage, an AI provider, or an integration endpoint.

## Durable State

State persisted to the durable source of truth so it survives process restarts and can be inspected later.

## Transient State

Short-lived runtime state used while a process is running, such as in-memory progress, temporary connection state, or local working data.

Durable state and transient state are different: durable state is part of the execution record, while transient state can be rebuilt or discarded.

## Correlation ID

An identifier carried through logs, events, tasks, and API calls so activity from the same execution or request can be traced across processes.
