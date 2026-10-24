# Task lifecycle

`axonx exec` resolves and validates an installed Task, then runs it in the current process through `TaskCommandExecutor` and `TaskRunner`. The service does not create queued records or start Task workers.

```text
exec → validate → queued → running → succeeded / failed
                        ↘ metadata, events, logs, artifacts
service → TaskRepository → read snapshots → API / Studio
```

The Runner creates Task and Run identity, publishes metadata atomically, executes synchronous steps and closes resources. Composite children execute in the same process and publish their own records. Metadata includes inputs, outputs, steps, children, process identity and artifact references.

A fixed name can replace a terminal record while retaining persistent data. A generated name creates a separate Task. Same-name concurrent operations require external coordination.

The service only observes the last published lifecycle snapshot. It does not inspect persisted PIDs to claim ownership, mark interrupted runs failed, or terminate Tasks during restart. A hard process kill can leave stale running metadata. Handle process control and any deliberate recovery outside the observing service.

`wait_task` checks an exact Task/Run pair; logs, streams, graphs and status queries do not own or control the execution. The dedicated submit, cancel and delete Tasks Jobs and service-worker handoff protocol have been removed without compatibility aliases. Task sources are `exec` or `unknown`.
