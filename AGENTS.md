# AxonX

Agent-native harness for quantitative research, with plugin-based Tasks and
CLI, HTTP, MCP, and Studio interfaces. See `CONTRIBUTING.md` for development setup
and contribution guidelines.

## Structure and Contracts

- `axonx/`: framework, Components, Jobs, CLI, service, and Task runtime.
- `plugins/`: research Tasks, algorithms, manifests, and plugin tests.
- `axonx_studio/`: React and TypeScript UI, API client, and research charts.
- `tests/`: framework unit and integration tests.
- `docs/`: bilingual guides and shared assets; `github-pages/`: site tooling.
- Keep research algorithms in plugins and reuse framework extension points.
- Preserve public CLI/API/configuration contracts, persisted task records,
  task identity, lifecycle behavior, and artifact formats unless changing them
  is part of the task. Document intentional compatibility changes.
- Preserve ownership and cleanup of async resources, streams, and subprocesses.

## Python and Plugins

- Use Python 3.12+ on macOS or Linux. Install with `pip install -e '.[dev]'`.
- Install relevant research dependencies with
  `axonx plugin install -e ./plugins/a158` or `./plugins/a158_enhanced`.
- Follow existing typing and style; Black uses a 120-character line length.
- Use temporary workspaces in tests and add focused regression tests for fixes.
- Run affected tests first, then `pytest` as appropriate. Bare `pytest` excludes
  integration tests and includes enhanced-plugin tests requiring plugin dependencies.
- Run `pre-commit run --files <changed-files>`; use `--all-files` for broad changes.
- Run `pytest -m integration` only when credentials and services are available
  and the tests' external effects have been reviewed.

## Studio

Run commands from `axonx_studio/`. Use npm and keep `package-lock.json` in sync.

- Install with `npm ci`; develop with `npm run dev` on port 4173.
- The dev proxy defaults to `http://127.0.0.1:1024`; override with
  `AXONX_DEV_SERVER` and restart Vite.
- Keep feature code in `src/features/`; reuse `src/shared/` API and SSE helpers.
- Preserve same-origin URLs, authentication, Job response handling, and selected
  machine `target`. Cancel obsolete requests and clean up polling and streams.
- New pages may need route, navigation, and outlet changes in `src/app/`.
- Use i18next; update both locale files with matching keys and placeholders.
- Reuse existing design tokens. Check both languages, themes, narrow layouts,
  empty data, and request failures for affected UI flows.
- For code changes, run `npm run test`, `npm run lint`,
  `npm run format:check`, and `npm run build`.
- Build before Python packaging: it includes existing `dist/` assets.
  npm's `prepack` builds automatically.

## Documentation and Generated Files

- Update English and Chinese documentation together when behavior changes.
- Edit canonical files under `docs/` or root/plugin READMEs and contribution
  guides. Site navigation lives in `docs/.vitepress/navigation.mjs`.
- For documentation or theme changes, run `npm ci` and `npm run build`
  from `github-pages/`.
- Do not hand-edit Studio `dist/`, `github-pages/.generated/`, or site `dist/`.
- Keep credentials, private data, runtime `.axonx/` contents, logs, and generated
  outputs out of commits. Format changed files without unrelated changes.
- Report validation commands, results, and any checks that could not run.
