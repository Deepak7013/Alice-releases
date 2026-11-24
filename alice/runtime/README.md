# Alice Runtime

The runtime is the durable bridge between Alice's reasoning layers and long-lived operation.

- `EventBus`: internal events for task completion/failure and future integrations.
- `ApprovalManager`: explicit approval queue for consequential actions.
- `AuditLog`: append-only JSONL activity history without storing model secrets/transcripts.
- `Scheduler`: persistent interval jobs with a 60-second minimum cadence.
- `AliceRuntime`: unified task submission boundary.

The scheduler intentionally uses bounded requests and does not bypass Alice's normal safety policy.
