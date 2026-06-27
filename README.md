# Revenue Captain Service

## Overview
This service uses an event-sourced state model. Instead of mutating rows in a database when a candidate’s status changes, the service reads an immutable event log from `events.json` and projects it onto the base state in `applications.json`.

## Core Components

### Hydrator (Normalization)
- Joins `applications.json`, `events.json`, and `school_routes.json`.
- Produces a single, cohesive `CandidateState` object.

### Rules Engine
- Evaluates hydrated state against business logic.
- Detects anomalies such as stale records, bounced communications, and missing evidence.
- Assigns a reason code for each detected state.

### Idempotent Worker
- Processes highest-priority next actions.
- Uses `application_id` and `target_state` as an idempotency key.
- Guarantees the same result whether the worker runs once or 100 times.

## Tradeoffs

### In-Memory vs. Database
- For this artifact, state projection happens in memory.
- In production, projecting state on the fly for millions of records is expensive.
- A more scalable production design would use a read-optimized materialized view (for example, in PostgreSQL) updated asynchronously by the event stream.

### Fuzzy Matching vs. Exact Match
- Duplicate detection currently assumes exact matching on `candidate_name` and `school`.
- Real-world applicant data is messy.
- A robust solution would use deterministic plus fuzzy matching, such as Levenshtein distance on names or normalized email matching.

## Production Hardening
To prepare this service for production, we can implement:

- **Idempotency keys via Redis**: Prevent duplicate actions from concurrent worker executions.
- **Dead Letter Queue (DLQ)**: Capture applications that cause unhandled exceptions during rule evaluation.
- **Alerting on stale states**: Trigger Datadog or Sentry alerts if a candidate remains in the actionable queue for more than 48 hours without a state transition.
