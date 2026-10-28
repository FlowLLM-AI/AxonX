# AGENTS.md

AxonX is a Python framework for agent-driven quantitative research, with a React/TypeScript Studio.
See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed workflows and [module-dependencies.md](module-dependencies.md) for architecture.

## Repository map

- `axonx/task/`: Task models, authoring bases, execution, storage, and built-ins.
- `axonx/app/`, `axonx/client/`: Application components, Jobs, services, and client connections.
- `axonx/cli/`, `axonx/daemon/`: Command routing, service supervision, and scheduled processes.
- `axonx/plugin/`, `plugins/`: Plugin infrastructure and research implementations, respectively.
- `axonx_studio/`: Frontend; `tests/`: framework tests; `docs/`, `github-pages/`: documentation and site tooling.

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
- Changed-file hooks: `pre-commit run --files <changed-files>`. Python uses Ruff import ordering and Black formatting.

Bare `pytest` also collects plugin tests and requires their research dependencies.
Integration tests are excluded by default; run `python -m pytest -m integration` only with the required services and credentials.

## Code conventions

- Keep code simple. Reuse existing logic, models, and concepts; extend them when needed. Remove unused code and merge duplicate implementations.
- Organize by capability within existing directories. Keep files cohesive without excessive splitting or oversized modules.
- Extend existing Component, Task, and Step contracts. Keep component base classes and concrete implementations; use classes for owned state and lifecycle, functions for simple transformations.
- Keep generic mechanisms and minimal protocols in the framework; put business research logic in plugins. Keep CLI thin, Task execution independent of App/Plugin/CLI, and Client independent of App.
- Use relative Python imports. Keep public exports and `__all__` in `__init__.py`, document direct submodules, and follow existing package entry points and explicit registration.
- Reuse Task identities and contracts. Distinguish upstream/downstream data dependencies from parent/child calls. Preserve scheduled task processes across service restarts.
- Breaking refactors are allowed: update affected callers together without legacy aliases or compatibility branches. Simplify redundant defensive logic while retaining necessary validation, cleanup, and consistency safeguards.

## Completing a change

- Respect the requested scope and preserve existing workspace changes. Map responsibilities and dependencies before broad refactoring; honor requests to analyze first.
- Update affected code, configuration, tests, comments, bilingual documentation, examples, Skills, and diagrams together. Describe the current implementation concisely.
- Run checks appropriate to the change and review the diff. Verify visible UI changes in a browser in both languages.
- Use temporary test workspaces. Keep credentials, private data, `.axonx/`, logs, and generated research outputs out of commits.
- Briefly report behavior changes, affected file responsibilities, checks run, and any remaining limitations.
