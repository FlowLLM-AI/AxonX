# AxonX

Agent-native quantitative research harness providing tools and a runtime for code
development, experiment execution, and result analysis. External or built-in Agents
use the AxonX Skill and user research prompts to develop or improve plugins.
Setup and contribution details: [CONTRIBUTING.md](CONTRIBUTING.md).

## Structure and Contracts

- `axonx/`: framework and runtime; `plugins/`: research Tasks and algorithms;
  `axonx_studio/`: React/TypeScript UI; `tests/`: framework tests;
  `docs/`: bilingual guides; `github-pages/`: site tooling.
- Python subsystem roots are `app`, `cli`, `daemon`, `cron`, `task`,
  `plugin`, and `common`. Keep service implementation in `app`; `task` must not
  import it. `common` must not import another subsystem. Standalone exec/kill and cron must not load App. Cron receives a launch
  callback; standalone daemon workers use only the standard library.
- `common` contains mechanisms and primitive data only. Task enums/log scopes live
  in `task`, component types and Studio schemas in `app`, provider registration
  in `common`, service configuration in `app/config`, shared config/runtime/connection/env
  mechanisms in `common`, and CLI parsing/help
  in `cli`. Cross-module usage does not change domain ownership.
- Shared workspace operations, previews and result models live in `common/workspace/`;
  import `Workspace` from the package and schemas from `.models`. App owns Job/HTTP
  adapters; Task owns metadata and execution policies. The base Workspace import
  must remain independent of Pydantic and optional file-format libraries.
- App must not import research plugins or Task builtins/runtime/catalog. Query Task definitions through a CLI subprocess. Local process reconciliation belongs to Task; generic identity/signals belong to Common. Metadata corrections and initial Run publication use short transactions; only confirmed dead original local Runs may be settled.
- Retain useful internal package structure. New imports use canonical module paths;
  obsolete pre-refactor module paths and compatibility-only facades are removed.
- Keep research algorithms in plugins; reuse framework extension points.
- Preserve public CLI/API/configuration contracts, persisted task records,
  task identity, lifecycle behavior, and artifact formats unless changing them
  is requested. Document intentional compatibility changes.
- Preserve ownership and cleanup of async resources, streams, and subprocesses.

## Agent Research Workflow

- Use [AxonX Skill](skills/axonx/SKILL.md) and the user's research objective for
  plugin development; Qlib Alpha158 is the reference workflow, and plugins can provide other methods.
- Keep plugin source changes, execution-service installation, and Task submission
  distinct. Verify the selected service's Task schemas and upstream artifact compatibility.
- For experiments, retain code/version, data, windows, parameters, costs, and Task/Run IDs.
  Distinguish implementation checks from evidence of research improvement.
- Canonical development instructions live in `docs/en/dev_guide.md` and
  `docs/zh/dev_guide.md`; keep the Skill's guide content aligned with the English source.

## Python and Plugins

- Use Python 3.12+ on macOS/Linux; match existing typing and Black's 120-character lines.
- Use temporary test workspaces and focused regression tests for fixes.
- From the repository root, run affected tests, then `pytest` as appropriate.
  Bare `pytest` excludes integration tests but includes factor and strategy plugin tests;
  install relevant plugin dependencies first (see CONTRIBUTING).
- Run `pytest -m integration` only with required credentials/services and reviewed external effects.
- Task and extension contracts: [Task guide](docs/en/dev_guide.md),
  [framework extensions](docs/en/development/framework-extensions.md).

## Studio

- From `axonx_studio/`, use Node per `package.json` engines and npm; keep `package-lock.json` in sync.
- Install: `npm ci`; dev: `npm run dev` (4173). Proxy: `http://127.0.0.1:1024`;
  override with `AXONX_DEV_SERVER` and restart Vite.
- Keep feature code in `src/features/`; reuse `src/shared/` API and SSE helpers.
- Preserve same-origin URLs, authentication, Job response handling, and selected
  machine `target`. Cancel obsolete requests and clean up polling and streams.
- Wire new pages through routes, navigation, and outlets in `src/app/` as needed.
- Use i18next; update both locale files with matching keys and placeholders.
- Reuse existing design tokens. Check both languages, themes, narrow layouts,
  empty data, and request failures for affected UI flows.
- For code changes, run `npm run test`, `npm run lint`,
  `npm run format:check`, and `npm run build`.
- Build before Python packaging (it bundles existing `dist/`); npm `prepack` builds automatically.
- API and UI details: [Studio development](docs/en/development/studio.md).

## Documentation and Delivery

- Update English and Chinese documentation together when behavior changes.
- Edit canonical `docs/`, READMEs, or contribution guides;
  navigation: `docs/.vitepress/navigation.mjs`.
- For site content/theme changes, run `npm ci` and `npm run build` from `github-pages/`.
- Do not hand-edit `axonx_studio/dist/`, `github-pages/.generated/`, or `github-pages/dist/`.
- Keep credentials, private data, runtime `.axonx/` contents, logs, and generated
  outputs out of commits. Format changed files without unrelated changes.
- Run `pre-commit run --files <changed-files>`; report checks, results, and anything not run.
