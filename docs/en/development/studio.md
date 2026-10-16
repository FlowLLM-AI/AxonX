# Extending Studio

This page explains how to add pages, forms, or charts to the existing Studio. For backend Task, Step, and Job extensions, see the [development guide](../dev_guide.md). For a first run, see [getting started with Studio](../getting-started/studio.md).

## Development environment

Start the service from the repository root, then run the frontend in another terminal:

```bash
cd axonx_studio
npm ci
npm run dev
```

The complete development toolchain requires Node.js 22.13+ (22.x), 24.x, or 26+ to satisfy the locked Vite, ESLint, and Vitest dependencies. Vite listens on 4173 by default, and the development proxy connects to `http://127.0.0.1:1024` by default. Use `AXONX_DEV_SERVER` to point to another backend and restart Vite after changing it. The proxy covers `/health`, `/jobs`, `/files`, `/mcp`, and `/proxy`.

`npm run build` performs TypeScript checks first, then outputs `dist`. Install the Python package with `pip install ./axonx_studio` from the repository root to let AxonX serve those assets. The development server provides hot updates.

If a mounted Studio build is removed while the service is running, page requests return `503` with a recovery message; missing asset requests return `404` or `503`. API routes remain available. Restore the build at the same path, or restart the service after changing the package installation path. This handles missing files before response headers are sent; it cannot replace a response whose transfer has already started.

## Directory responsibilities

| Location            | Responsibility                                                                           |
| ------------------- | ---------------------------------------------------------------------------------------- |
| `src/app`           | Hash routing, navigation, machine selection, page dispatch, and shared application state |
| `src/features`      | Business pages for submission, run center, Agent, research, and workspace                |
| `src/shared/api`    | Job requests, response unwrapping, SSE, and shared types                                 |
| `src/shared/schema` | JSON Schema field types and form-value conversion                                        |
| `src/shared/ui`     | Reusable components such as SchemaForm and panel dragging                                |
| `src/shared/hooks`  | Asynchronous loading, polling, and copy feedback                                         |
| `src/styles`        | Design variables, shell, and feature styles                                              |
| `src/locales`       | Chinese and English translation resources                                                |

![Studio feature map](../../figures/getting-started/studio-map.svg)

## Adding a page

Routes use `#<machineId>/<section>/<view>/<resource>`. For example, `#local/task-defs/catalog/demo` identifies the local demo submission form. `routeHash` encodes resource identifiers and `parseHash` decodes them; do not manually concatenate Task IDs containing `#`.

1. Create the page, necessary types, and API wrappers in `features/<feature>`.
2. Register the section and default view in `app/routes.ts`.
3. Add navigation entries in `app/navigation.ts`.
4. Connect page dispatch in `app/PageOutlet.tsx` and pass the selected machine.
5. Add user-visible text to both locales; keep the corresponding Chinese and English documentation in sync.

Distinguish page route state from temporary UI state. Shareable resource selections suit the Hash; expanded panels and loading progress belong in component state. Invalid sections return to the home page.

## Calling the backend

Call Jobs consistently through `axonx.invoke` in `shared/api/client.ts` or an existing feature API wrapper:

```typescript
const definitions = await axonx.invoke(
  "list_installed_task_definitions",
  {},
  { target: selectedMachine, signal: controller.signal },
);
```

The request body is `{ arguments, target }`, and the outer response is JobResponse. The client handles HTTP errors and `success: false` centrally; business pages receive the unwrapped `answer`. Return types should reflect the actual backend protocol. Do not hide protocol differences with forced type assertions.

Machine selection must carry through lists, details, submission, and file previews. Same-origin `/jobs` requests include the service token from browser settings; the backend resolves remote target addresses and credentials. See the [machine guide](../guides/remote-machines.md).

## Forms and real-time state

Prefer reusing SchemaForm. Integer and floating-point fields become numbers, enums decode from JSON values, array and object inputs use JSON, and empty optional fields are omitted. Optional Boolean fields without defaults are also omitted when off. The server remains responsible for final validation.

Pass AbortSignal to cancel stale requests. Reuse `usePolling` for list polling and the SSE parser for long-task events. Completion of a Job call does not mean a background Task has finished. See [real-time events](../api/events.md) for the event protocol.

Agent tool cards show accumulated JSON argument fragments while input is streaming. A complete tool message updates the existing card with formatted input and clears the partial text, so commands remain visible during execution without waiting for the end-of-turn history reload.

Task details use four independent cards: configuration, relations, run details, and logs. The available page width selects two columns or one. Each card has a bounded content viewport; overflowing content scrolls vertically and horizontally, and log lines retain their original formatting.

## Charts and files

Research pages read task artifacts. New calculations should follow explicit definitions and explain differences from plugin summaries. See the [research artifact reference](../reference/research-artifacts.md) for the sources of training curves, returns, holdings, and other fields. Missing files and empty data should have clear empty states.

Keep file previews workspace-relative. `/files` provides temporary uploads and cleanup, not general downloads; obtain complete artifacts from the execution machine's workspace. Do not concatenate server absolute paths into public UI. On pages with multiple charts, handle container resize and release resources on component unmount.

## Verification and submission

```bash
npm run test
npm run lint
npm run format:check
npm run build
```

Choose relevant tests for the changes. Existing tests cover routing, Schema value conversion, event parsing, and request unwrapping and can be extended. UI checks should at least cover English and Chinese, empty data, loading failures, long text, and narrow windows. Do not expose tokens, private sessions, task identifiers, or machine addresses in screenshots.

When updating user documentation, also add feature entry points, prerequisites, steps, and failure handling. Screenshots and SVGs use English, and screenshots must not contain credentials, private paths, or session content.

## Implementation references

- `axonx_studio/src/app/routes.ts`, `PageOutlet.tsx`, `navigation.ts`
- `axonx_studio/src/shared/api/client.ts`, `event.ts`
- `axonx_studio/src/shared/schema/values.ts`
- `axonx_studio/vite.config.ts`, `package.json`

## Static Playground

The website includes a standalone Studio at `/AxonX/playground/`. It uses the same pages, Job envelopes and SSE parser as the service-backed application. No Python service, database or LLM is involved. Securities and research results are synthetic. Agent replies are scripted.

```bash
npm ci
npm run dev:playground
# Open http://localhost:4173/AxonX/playground/
npm run build:playground
```

`DOCS_BASE` determines the mount prefix (default `/AxonX/`). The separate `dist-playground/` output leaves the ordinary `dist/` used by Python packaging untouched. The documentation build constructs and merges this output into its Pages artifact. Install dependencies in both `axonx_studio/` and `github-pages/` before building the website.

All requests, including streams, go through `AxonXClient.request`. The default transport calls same-origin HTTP; `main.tsx` injects `createPlayground()` before mounting in Playground mode. Authentication is disabled for this simulated client. Feature API wrappers do not branch on mode. Unknown Jobs, files and remote targets return explicit errors without network fallback.

`playground/fixtures.ts` creates a virtual workspace with an ETL → training → prediction → backtest chain, independent factor analysis from ETL, and two backtests. JSON table previews implement the existing Parquet preview protocol without shipping a Parquet decoder. Returns and summary metrics are generated from the same series.

`playground/runtime.ts` owns task and file state; `agent.ts` owns scripted sessions and tool messages; `stream.ts` owns event subscription cleanup; `catalog.ts` declares supported Jobs. Submitted tasks advance from elapsed time even without subscribers; status requests and streams reconcile that state. Task cancellation stops execution, while AbortSignal only closes an obsolete subscription and releases its timer. All states have unified metadata; successful runs add business artifacts. The `strategy` parameter selects synthetic results; `outcome` selects success or failure. No submitted configuration executes a real research algorithm.

Refresh or use **Reset demo** to recreate initial state. There is no persisted execution state. Tests exercise data contracts, pagination, lifecycle, deletion, stream cleanup, scripted conversations and network isolation. Verify both normal and Playground builds; the website verifier checks the merged Playground entry and asset paths.

## Application operations pages

The sidebar order is **System management → Daily operations → Research → Development tools**. System management contains all tasks, machine resources and environment; daily operations defaults to online prediction, comparison, data updates and synchronization. Research starts with Agent and follows ETL → factors → training → prediction → backtest → strategy comparison. Development tools contains task submission, workspace and API interfaces. System management and daily operations are expanded by default; the other groups start collapsed. Group preferences persist in browser local storage. Entering a page expands its group, including direct links; the current group can still be collapsed manually. Applications control operations item order through the insertion order of `studio.pages`.

`default.yaml` declares four generic pages (sync, data, online, comparison). Applications bind schedules and override labels through `studio.pages`; AxonX exposes them through the authenticated, target-aware `list_studio_pages` Job. The selected service owns navigation: AxonX does not hardcode plugin Task names or schedule names. Pages appear under **Daily operations** and use `#local/operations/<page-id>`. The old mixed `online/runs` route is removed. Standalone reports use `#local/report/task/<encoded-task-id>`.

```yaml
studio:
  pages:
    downloads:
      title: { en: Data updates, zh: 数据更新 }
      view: tasks
      schedules: [daily_download]
      category: data_update
```

Use `view: schedules` for Job-only schedules (no category; an empty schedule list shows no configured sync jobs), `tasks` for Task progress and recursive child logs, or `pipeline` for online/comparison reports. Task pages require a `TaskCategory`: `data_update`, `online_prediction` or `comparison`. Plugin classes declare `category = TaskCategory.DATA_UPDATE`, for example. Category is independent of `TaskType`, storage identity and `report_kind`; the same composite execution type can belong to different operational pages. Categories are published in installed definitions, queued metadata, running metadata and summaries. Existing records without a category stay in **All tasks**; rerun to produce categorized records. Composite children retain their category and record `parent_run_id`; page indexes show only root invocations. Manual root runs appear alongside scheduled ones.

The index groups execution records under their schedules, with manual Task runs in a separate group. Click a schedule name to inspect its configuration; use its arrow to collapse its records. Selection changes only the detail panel and never hides other groups. Association uses schedule name, Job, scheduler identity and persisted trigger provenance. Unmatched scheduled Tasks appear under a historical schedule, not under manual runs. A trigger with an available Task appears once as that Task; other triggers remain inspectable Job executions. Unknown page IDs and unavailable services have explicit empty/error states. Navigation reloads on machine or credential changes and refreshes every minute; page data, child progress and logs poll every five seconds, including while idle.

Cron schedulers atomically persist trigger state and bounded results under `workspace/schedules/<sha256-name>.json`: all active triggers and the latest 50 finished triggers. Results exceeding 16 KiB are represented by a truncated summary. Finished records survive service restart; unfinished records are marked cancelled with an interruption reason. Scheduler IDs remain process-specific. The schedule page displays last result metrics, errors, completion time and individual trigger details; scheduled Job success means the Job finished, while a submitted Task has its own lifecycle. Task records and artifacts keep their existing persistence semantics: a same-name rerun replaces the current Run.

Online reports show realtime collection, historical preparation and timed model inference. Comparison reports show shared downloads, per-model ETL, online-source checks, prediction differences and backtests. They share reporting components but have separate configured pages. Child details and selectable logs match both Task ID and exact Run ID; replaced runs cannot supply another invocation's results. Signal publication remains distinct from execution status.

Run `npm run dev:playground` and open `http://localhost:4173/AxonX/playground/#local/operations/online` for synthetic operations examples. The sync, data and nightly pages are independent examples; Playground resets on reload and does not demonstrate disk persistence or execute plugin algorithms.
