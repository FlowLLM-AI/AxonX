# Module boundaries and execution-state refactor

Seven subsystem roots remain, preserving useful App/Task subpackages. This pass deliberately removes compatibility paths and implicit capabilities.

| Module | Responsibility                                                                                                                                                                                                                 |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| app    | Service configuration/composition, component lifecycle, Jobs/Agents, HTTP/MCP/SSE, workspace and Task observation/subscriptions                                                                                                |
| cli    | start, exec, kill, Task definitions, plugin commands and explicit remote forwarding                                                                                                                                            |
| daemon | Service/cron supervision, reaping launched children and update workers                                                                                                                                                         |
| cron   | Configuration parsing and future triggers, handing launch to an injected callback                                                                                                                                              |
| task   | Authoring/execution, pure contracts, storage, queries, process reconciliation and artifact replication                                                                                                                         |
| plugin | Task-only manifests, discovery, build/validation, installation and removal                                                                                                                                                     |
| common | Generic configuration loading, environment/runtime/connection settings, provider registration, machine/process identity, exact process signals/waits, file locks/atomic writes, logging, argument conversion and async cleanup |

## Intentional breaking changes

- Group shared Workspace operations, previews and result schemas under `common/workspace/{core,preview,models}.py`. The package exports `Workspace` without importing Pydantic; result models are imported explicitly from `.models`. Remove the old flat preview module and `app/workspace/`; keep App adapters and Task policies with their owners.
- Merge `axonx/config/` and `app/config.py` into `app/config/`: App models, resolver and built-in YAML. Generic `ConfigLoader`, dotenv, file/entry-point lookup, runtime and connection settings move to Common; CLI output options stay in `cli/options.py`. Remove old module paths. Independent exec/kill read environment and defaults, without loading service YAML; cron reads YAML through Common before any App import.
- Remove `app/core/plugin_runtime.py`, `app/steps/plugin/` and the four plugin management Jobs. Remove startup `plugins.sources`, `PluginConfig`, plugin Component/Job contributions and the staged-install bypass.
- App does not import `plugin` or Task builtins/runtime/catalog. Definition APIs use a CLI subprocess and a JSON boundary to inspect the current installed environment.
- Shared registration moves to `common/registry.py`; process identity and signal primitives move to `common/process.py`, with no old re-exports. Explicit `Application(providers=...)` plus component/Job configuration extends services.
- Task package exports are lazy. Incremental metadata scans live in `task/storage/index.py`; ancestor/context calculation lives in `task/query/context.py`. App owns polling, caching, calls and transport.
- Remove `queued`. Metadata requires machine ID, positive PID and timezone-aware process creation time; initial execution records are `running`. Display replicas retain source identity and prohibit local control through their replica marker.
- `task/storage/records.py` shares local liveness checks, failure settlement, conflict messages and explicit kill. Startup/polling checks unchanged active records too; foreign, replica and permission-unknown records are not rewritten.
- Initial publication and reconciliation use short transactions, with no execution-long lock. Reruns log `Overwrite` and retain `persistent/`. Kill binds the Run ID, defaults to SIGTERM and requires explicit force escalation.

## Verification scope

Run focused/full Python tests, real subprocess and CLI/HTTP checks and isolated-import boundaries. Update Studio contracts/state views and run tests, lint, formatting and build. Check bilingual docs, wheels/sdists and installation outside the checkout, then scoped pre-commit. Credential-dependent integration, paid models and remote deployment are outside this pass.

See [Task lifecycle](../concepts/task-lifecycle.md) for state semantics.

## Completion evidence

- Full Python suite: 794 passed, 2 deselected, covering real termination, timeout/force retry, PID reuse, replacement-Run protection, foreign/replica refusal, periodic checks and remote CLI.
- Studio: 275 tests passed; lint, formatting and production build passed. Python/TypeScript contracts match.
- Bilingual documentation build and scoped pre-commit passed.
- Core, Studio and three research plugins built wheels/sdists. Distribution contents match source, without obsolete modules. Five wheels were installed outside the checkout in a temporary virtual environment using existing dependencies (system-site-packages, no-deps).
- Installed smoke checks cover exec, Overwrite/persistent retention, definitions, exact kill, plugin-free App observation and Studio HTTP assets.
- Credential-dependent integration, paid models and remote deployment were not performed.
