# AGENTS.md

AxonX 0.3.0 is a Python framework for agent-driven quantitative research, with a React/TypeScript Studio.
See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed workflows and [module-dependencies.md](module-dependencies.md) for architecture.

## Repository map

- `axonx/task/`: Task models, authoring bases, execution, storage, and built-ins.
- `axonx/app/`: `config` models/loading, `core` composition/dispatch, `components` capabilities, `steps` Job adapters, and `workspace` file access.
- `axonx/client/`: Independent HTTP/MCP clients, connection settings, and public Job/event contracts.
- `axonx/cli/`, `axonx/daemon/`: Command routing, service supervision, and scheduled processes.
- `axonx/plugin/`, `plugins/`: Plugin infrastructure and research implementations, respectively.
- `axonx/utils/`: Shared environment loading, scalar conversion, logging, and cancellation-safe async work.
- `axonx_studio/`: Frontend; `tests/`: framework tests; `docs/`, `github-pages/`: documentation and site tooling.
- `scripts/`: Contract generation, Agent guide synchronization, and deployment tooling; `skills/axonx/`: generated distributable development Skill.

## Runtime and configuration

- `axonx/_version.py` owns the main package version. Studio has independent Python/npm version metadata.
- `axonx app --config NAME_OR_PATH` loads YAML/YML/JSON, bundled names, or installed `axonx.configs` entries. Custom files inherit defaults only with `extends: default`; mappings merge recursively, lists/scalars replace.
- CLI startup loads the nearest `.env` without overwriting existing environment values. `example.env` documents the variables consumed by bundled configs and built-ins; execution settings use CLI options > service `get_config` > `ExecutionSettings` defaults.
- `axonx exec` runs Tasks synchronously; remote exec/kill/plugin operations use the service's `cli` Job. `help` queries a service; `--help` is offline. Task definitions reflect the selected execution environment.
- Cron is an App component configured through the top-level `cron` list. It launches daemon-owned local `axonx exec --task NAME` processes, which survive service restarts; service-owned manual CLI commands stop with the service.

## Development and checks

Use Python 3.12+ on macOS/Linux. Studio requires Node.js 22.13+ within 22.x, 24.x, or 26+.
Run Python commands from the repository root and npm commands from the indicated package.

- Python setup: `python -m pip install -e '.[dev]'`.
- Studio setup and development, in `axonx_studio/`: `npm ci`, then `npm run dev`.
- Python: run affected tests first; use `python -m pytest tests` for the framework suite.
- Plugins: run the affected plugin's tests, e.g. `python -m pytest plugins/qlib_factor/tests`.
- Studio: `npm test`, `npm run lint`, `npm run format:check`, and `npm run build`.
- Wire contract changes: in `axonx_studio/`, run `npm run contracts:generate` and `npm run contracts:check`; do not hand-edit generated contracts.
- Documentation examples: `python -m pytest tests/unit/test_documentation_contracts.py`. Site checks: `npm --prefix github-pages test` and `npm --prefix github-pages run build`, after installing both frontend dependency sets.
- Agent guides: edit `docs/{en,zh}/dev_guide.md`, run `python -m scripts.sync_agent_guides`, then `python -m scripts.sync_agent_guides --check`. Packaged guides and `skills/axonx/SKILL.md` are generated standalone files.
- Changed-file hooks: `pre-commit run --files <changed-files>`. Python uses Ruff import ordering and Black formatting.

Bare `pytest` also collects plugin tests and requires their research dependencies.
Integration tests are deselected by default; run `python -m pytest tests/integration -m integration` only with the required services and credentials.

## Code conventions

- Keep code simple. Reuse existing logic, models, and concepts; extend them when needed. Remove unused code and merge duplicate implementations.
- Organize by capability within existing directories. Keep files cohesive without excessive splitting or oversized modules.
- Extend existing Component, Task, and Step contracts. Keep component base classes and concrete implementations; use classes for owned state and lifecycle, functions for simple transformations.
- Keep generic mechanisms and minimal protocols in the framework; put business research logic in plugins. Keep CLI thin, Task execution independent of App/Plugin/CLI, and Client independent of App.
- Keep Task models data-only and preserve `runtime → builtins/core/storage/models`, `builtins → core/storage/models`, `core → storage/models`, and `storage → models`. App composition owns concrete Provider selection; Steps depend on component base contracts.
- Use relative Python imports. Keep public exports and `__all__` in `__init__.py`, document direct submodules, and follow existing package entry points and explicit registration.
- Reuse Task identities and contracts. Distinguish upstream/downstream data dependencies from parent/child calls. Preserve scheduled task processes across service restarts.
- Breaking refactors are allowed: update affected callers together without legacy aliases or compatibility branches. Simplify redundant defensive logic while retaining necessary validation, cleanup, and consistency safeguards.

## Completing a change

- Respect the requested scope and preserve existing workspace changes. Map responsibilities and dependencies before broad refactoring; honor requests to analyze first.
- Update affected code, configuration, tests, comments, bilingual documentation, examples, Skills, and diagrams together. Describe the current implementation concisely.
- Write documentation and examples directly against the current code and protocols. Do not add upgrade guides, legacy aliases, or compatibility branches.
- Keep generated `axonx_studio/src/shared/api/contracts.ts` and `axonx_studio/src/playground/job-contracts.json` synchronized with Python models, default Job config, and version metadata.
- Run checks appropriate to the change and review the diff. Verify visible UI changes in a browser in both languages.
- Use temporary test workspaces. Keep credentials, private data, `.axonx/`, logs, and generated research outputs out of commits.
- Briefly report behavior changes, affected file responsibilities, checks run, and any remaining limitations.
