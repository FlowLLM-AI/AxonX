# Eight-module refactor

The Python package now has eight independently owned modules, with old internal import paths and compatibility-only modules removed. Task IDs, lifecycle records, artifacts and configuration data retain their existing meaning; Python imports and execution APIs, plus the Job help usage field, change as described below.

## Capability inventory and changes

| Module   | Owned capabilities                                                                                                                                    | Refactor and simplification                                                                                                                                 |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app`    | Application composition, components, Jobs and Steps, HTTP/MCP/SSE, agents, service-side repositories, workspace operations and remote synchronization | Move existing service code together, retaining its internal structure. Keep application-specific plugin composition here.                                   |
| `cli`    | Command dispatch, local exec/plugin/start commands and output rendering                                                                               | Import subsystems only for the selected command. Keep shared argv parsing outside the executable entry point.                                               |
| `daemon` | Supervision, owned subprocesses, local control protocol and update execution                                                                          | Keep standalone workers independent of application imports. Move the update worker beside its process owner.                                                |
| `cron`   | Crontab configuration, parsing, next-occurrence calculation and triggering                                                                            | Reuse shared argument validation and inject the launch callback instead of importing the daemon.                                                            |
| `config` | Provider/runtime/connection schemas, dotenv, configuration lookup, inheritance and merging                                                            | Retain declarative schemas; share scalar conversion and remove historical resolver re-exports.                                                              |
| `task`   | Task authoring and composition, catalog, execution, lifecycle, artifacts, queries, replica processing, research contracts and built-ins               | Preserve internal directories. Own Task events, reuse argument parsing and remove obsolete import facades and unused helpers.                               |
| `plugin` | Manifest and contribution data, installed discovery, identity, wheel building, installation, removal and symbol loading                               | Rename `plugin_kit`; move CLI handling and application composition to their owners. Reuse artifact preparation instead of duplicating wheel/build handling. |
| `common` | Filesystem primitives, logging, generic argument conversion and primitive log data                                                                    | No imports of the other seven modules. Keep domain-specific implementation and constants with their owners.                                                 |

`app` may depend on `task`, `plugin`, `config`, `common` and the daemon control protocol. `task` may depend on `plugin`, declarative `config` and `common`. `plugin` may depend on declarative `config` schemas and `common`. `config` and `cron` may depend on `common`; cron also uses configuration lookup. `cli` is the composition entry point. Daemon workers remain standalone standard-library programs. Package initializers must not eagerly import unrelated subsystems.

## Internal capability ownership

- **App:** `core` owns composition, dependency order, context and dispatch; `components` owns agents/session stores, clients, Jobs, proxies, HTTP services, repositories, network synchronization and update requests; `steps` exposes these operations; `workspace` owns browsing, previews, deletion and staging.
- **CLI:** dispatch selects service startup, independent Task execution, plugin commands or remote Job calls. Rendering owns the startup banner, JSON and streamed presentation. The CLI owns full parsing; the remote gateway launches the CLI subprocess, whose entry point rejects forbidden startup or nested targets.
- **Daemon:** the local client owns launch/control exchanges; the standalone supervisor owns worker readiness, replacement, reaping and update state; the standalone update worker owns build/install subprocess cleanup.
- **Cron:** code and `.cron` resources share the module. Parsing, named-file lookup, timezone-aware next occurrences and future-trigger cleanup remain; the supplied launch callback owns the process handoff.
- **Config:** models describe runtime settings, components, Jobs, targets and plugins; App owns application and Studio validation; the resolver owns inheritance, environment expansion and deep merging; the locator owns explicit paths, built-in names and installed entry points.
- **Task:** core authoring/identity/composition, catalog, executor/runner, pure schemas, metadata/log/event storage, pinned inputs/models/online publications, graph/summary/follow queries, bounded display replicas, research contracts, event replay and stock/Tushare/DingTalk built-ins remain independently usable.
- **Plugin:** provider registration, manifests and contribution indexes describe public names; discovery and identity describe installed/wheel content; artifact preparation, building, installation and removal own package mutation; symbol loading validates only the base class supplied by its caller.
- **Common:** scalar/nested-option conversion, primitive log data, filesystem safety/atomicity/revisions/hashes, basic process logging and cancellation-safe blocking work. This module owns no service, Task launch, scheduler or plugin installation policy.

## Execution plan

1. Establish the baseline and capture serialized contracts.
2. Move the existing package trees and update Python imports, plugin sources, packaging and documentation paths.
3. Separate shared command parsing, Task events, registry and filesystem paths from service implementation.
4. Remove compatibility-only files, unused functions and duplicated argument/artifact preparation logic.
5. Verify allowed dependencies, fresh-process imports and real CLI entry points.
6. Run affected and full Python tests, contract checks, package smoke checks, documentation build and scoped pre-commit checks.

The baseline is **774 passed, 2 deselected** with `PYTHONPATH=. python -m pytest -q`. Integration tests requiring credentials or external services are excluded.

## Completion evidence

- The eight roots and existing useful App/Task subpackages are in place. `plugin_kit` and obsolete package paths are removed.
- Shared scalar/argv parsing and plugin artifact preparation now have one implementation. Nine Task import facades, unused Task argv helpers and the unused demo Job Step were removed. Task, plugin and HTTP constants have explicit owners.
- Framework Python source changed from **231 files / 17,768 lines** to **228 files / 17,262 lines**, a net reduction of **506 lines**.
- Full Python regression: **760 passed, 2 deselected**. The previous compatibility-path checks were replaced by dependency and fresh-import checks. A real CLI exec completed without importing App/FastAPI.
- All **51 serialized model schemas** exactly match the pre-refactor snapshot; Studio contract generation check passed.
- Studio: **275 tests passed**; lint, format check and production build passed.
- Documentation: build passed, verifying **124 guides and 508 local links/assets**, bilingual navigation, source links and exports.
- Core and three research plugins built wheels and sdists; distribution-content checks passed. All four wheels were installed and verified outside the checkout in a temporary virtual environment using the existing dependency environment (`--system-site-packages`, `--no-deps`).
- Scoped pre-commit passed, including Python lint/format, documentation formatting and Studio contracts. Credential-dependent integration tests, paid-model calls and remote deployment were not performed.

## Common ownership refinement

This second pass removes the old Common locations without aliases. Common uses at most two directory levels: `fs/` contains filesystem primitives; `logging.py`, `logs.py`, `async_work.py`, `arguments.py` and `constants.py` live directly in Common. The generic `utils/` export layer is removed:

| Capability                                                                              | Owner                                                                            |
| --------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Task state/type/category enums and Run log scopes                                       | `task/enums.py`, `task/runtime/logging.py`                                       |
| Component categories, application/Studio schemas, build diagnostics and log retention   | `app/components/types.py`, `app/config.py`, `app/core/`                          |
| Provider declarations and registry                                                      | `plugin/registry.py`, accepting plain category strings                           |
| Connection options/address rules, environment files, execution environment and defaults | `config/target.py`, `config/env.py`, `config/execution.py`, `config/defaults.py` |
| CLI Command/argv parsing and usage text                                                 | `cli/parser.py`, `cli/usage.py`                                                  |
| Root path confinement                                                                   | `common/fs/paths.py::ConfinedPaths`                                              |
| Upload naming and staging policy                                                        | `app/workspace/paths.py::WorkspacePaths`                                         |

`config.RuntimeConfig` contains only process settings; `app.config.ApplicationConfig` owns service and Studio validation, keeping `config` and `plugin` independent of Task imports. Task execution is `TaskExecutor.execute(name, inputs) -> TaskMetadata`; CLI raw argv is `Command.raw_arguments` rather than a hidden business argument. The Job help response no longer includes CLI usage. The unused `file_versions` helper and its isolated tests are removed. Task identity, lifecycle/artifact formats and all 51 serialized model schemas remain unchanged.

Common shrinks from **26 Python files / 1,309 lines** to **13 files / 518 lines**, removing **791 lines**. The full suite passes **760 tests**, including module dependency rules, isolated imports, the execution API, log cleanup and real remote CLI forwarding. Removed tests covered deleted compatibility paths or unused APIs; module boundaries and persisted execution results now enforce the intended contracts.
