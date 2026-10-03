# AxonX

Agent-native quantitative research harness with plugin-based Tasks and CLI, HTTP,
MCP, and Studio interfaces. Setup and contribution details: [CONTRIBUTING.md](CONTRIBUTING.md).

## Structure and Contracts

- `axonx/`: framework and runtime; `plugins/`: research Tasks and algorithms;
  `axonx_studio/`: React/TypeScript UI; `tests/`: framework tests;
  `docs/`: bilingual guides; `github-pages/`: site tooling.
- Keep research algorithms in plugins; reuse framework extension points.
- Preserve public CLI/API/configuration contracts, persisted task records,
  task identity, lifecycle behavior, and artifact formats unless changing them
  is requested. Document intentional compatibility changes.
- Preserve ownership and cleanup of async resources, streams, and subprocesses.

## Python and Plugins

- Use Python 3.12+ on macOS/Linux; match existing typing and Black's 120-character lines.
- Use temporary test workspaces and focused regression tests for fixes.
- From the repository root, run affected tests, then `pytest` as appropriate.
  Bare `pytest` excludes integration tests but includes enhanced-plugin tests;
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
