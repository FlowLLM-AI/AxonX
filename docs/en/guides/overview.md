# Operations and deployment

Manage the service, execution target, and persistent research records as separate responsibilities. First verify a local connection with the [quickstart](../getting-started/quickstart.md), then choose the operation you need.

## Choose an operation

| Goal                                              | Guide                                                          |
| ------------------------------------------------- | -------------------------------------------------------------- |
| Execute, wait, follow logs, stop, or delete Tasks | [Task management](task-management.md)                          |
| Combine installed Tasks into a synchronous flow   | [Composite Tasks](composite-tasks.md)                          |
| Browse and inspect workspace artifacts            | [Workspace files](../concepts/workspace.md#browse-directories) |
| Copy completed Task snapshots                     | [Task synchronization](task-sync.md)                           |
| Configure service access and tokens               | [Authentication](authentication.md)                            |
| Host a service with or without Studio             | [Deployment](deployment.md)                                    |
| Use CLI direct access or Studio forwarding        | [Remote machines](deployment.md#remote-connections)            |
| Forward configured HTTP requests                  | [HTTP proxy](http-proxy.md)                                    |
| Schedule recurring local Task commands            | [Scheduling](scheduling.md)                                    |
| Send task notifications through DingTalk          | [Notifications](../research/notifications.md)                  |
| Diagnose failures, back up, and recover records   | [Troubleshooting and recovery](operations.md)                  |

## Establish the execution environment

Each execution target has its own Python environment, plugins, data, and workspace. Direct CLI access uses the target service token; Studio uses the local token and forwards through its same-origin backend to a configured target. Use the same execution target for execution, waiting, logs, and artifact queries.

Task synchronization copies terminal display snapshots and optional live parent/child groups; replicas cannot be research inputs. Prepare raw data, plugin dependencies, model credentials, and Agent session environments separately. See [workspace concepts](../concepts/workspace.md) for storage boundaries and [client configuration](../reference/client-configuration.md) for connection precedence.

## Preserve evidence while maintaining the service

Retain distinct Task identities for experiments. A fixed-name rerun replaces a finished directory; deletion removes records and artifacts. Explicit Task termination stops execution. The default remote cli Job continues after client disconnection; service shutdown stops its manual commands without resuming them later. Daemon-owned scheduled commands survive service restart. Read [task lifecycle](../concepts/jobs-and-tasks.md) before choosing cleanup or recovery actions.
