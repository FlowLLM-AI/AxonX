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

Use `src/shared/ui/Select.tsx` for single-value dropdowns. `Select` preserves native option markup, change events and form validation; `Picker` accepts an option list for labelled toolbar controls. Both share the same themed menu, keyboard navigation and viewport-aware positioning in `styles/select.css`. Do not add visible native selects or duplicate menu implementations.

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

Pass AbortSignal to cancel stale requests. Reuse the shared `useRefresh` scheduler for polling and the SSE parser for long-task events. Completion of a Job call does not mean a background Task has finished. See [real-time events](../api/events.md) for the event protocol.

Agent tool cards show accumulated JSON argument fragments while input is streaming. A complete tool message updates the existing card with formatted input and clears the partial text, so commands remain visible during execution without waiting for the end-of-turn history reload.

Task details use four tabs with title icons: configuration, relations, run details (selected initially), and logs. Switching tabs preserves log and report controls. The shared async resource hook cancels obsolete requests and hides the previous selection when the Task or machine changes; late cancellation responses cannot reload an old selection. Run details show only steps for ordinary Tasks, including indented substeps; composite Tasks show only their direct child Tasks with status and navigation, using the latest invocation per node. Child details are opened in their own Task page. Business reports, quality, files and raw outputs are accessed through dedicated report pages. Consecutive completed steps with the same name are collapsed into an expandable count; completion follows step state, so a running step at 100% remains active. Running and failed steps remain individually visible. Each tab fills the remaining screen height and scrolls overflowing content internally; log lines retain their original formatting.

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

The index groups execution records directly under their schedule names. Task runs without schedule provenance appear as flat rows, without an extra source heading or empty group. Click a schedule name to inspect its configuration; use its arrow to collapse its records. Selection changes only the detail panel and never hides other groups. Association uses schedule name, Job, scheduler identity and persisted trigger provenance. Unmatched scheduled Tasks appear under a historical schedule, not under manual runs. A trigger with an available Task appears once as that Task. Successful `submit` executions without retained Tasks are omitted from the history rail; unmatched running, failed or cancelled submissions remain visible for diagnosis. A matching Task replaces its submission row. Submission status, errors and the latest result remain available in the schedule details, and persisted history is unchanged. Other Job executions remain visible. Unknown page IDs and unavailable services have explicit empty/error states. Navigation reloads on initial entry, machine or credential changes, or explicit navigation reload. Studio uses one shared 60-second scheduler for service health, task lists, reports, child progress and logs. Returning to a visible window does not trigger an extra refresh. Each daily operations page has one manual refresh button in its history rail that refreshes the whole page. Refreshing preserves the selected tabs.

Daily operation pages share a compact history rail and an open report canvas, matching offline research. Data updates combine result/log navigation and a download task picker in one toolbar; other operation pages retain their report navigation. Comparison reports initially show model stages; refreshing preserves the selected tab, and switching tabs preserves log and report controls. Collection quality reports appear inside their matching collection step instead of a separate list. Collection cards show files directly. Online prediction groups quality by source in the second tab row. Quality details and full-report provenance expand inline; reports do not use side panels. Model stages and child Task reports display directly; quality summary artifacts load when their source is opened, while full detail artifacts load when expanded. Committed files are always visible as compact filename links to the selected machine’s workspace preview. Absolute recorded paths are mapped against the root returned by that workspace; when older services omit the root from directory listings, Studio retrieves it from the selected machine’s diagnostics. Paths outside the root remain unavailable. Schedule details separate cron/timezone/policy, trigger times and result metrics; execution records show their name, time and status. Online and comparison pages use the same report spacing, stage cards and log toolbar. A schedule header status describes its latest Job execution, while each Task keeps its own status.

Online prediction uses at most two tab rows for a selected trading date. The first row places a separate Preparation entry beside a framed signal-time sequence. Small chevrons connect adjacent times inside the frame. Each time shows Completed, Failed, Preparing data, Ready to run, Running or Awaiting preparation; collection before/bar records share the same time. Preparation contains Base collection, Shared ETL when independent ETL exists, Opening quotes and Logs. A signal time uses seven entries: Collection, Model preparation, Predictions, Pre-signal quotes, Current-bar quotes, Model input and Logs. Model preparation combines historical inputs, features and provenance, with completed history reuse summarized in one row; Predictions combines scoring, signals and portfolio results. History preparation belongs to a model and signal time; its failure affects that time rather than shared preparation. The model dropdown sits at the upper right and retains the selected model name across times; model stages and logs follow it while shared collection stays common. ETL owned by history preparation remains there instead of appearing again under Shared ETL. A time's status prioritizes failures in any required stage or model. Historical preparation alone shows Preparing data; active collection or inference shows Running. Ready to run requires explicit completed history preparation for every planned model while collection/inference is still pending. Awaiting preparation means preparation has not started or its state is not yet confirmed; missing or partially completed history records never imply readiness. A pending window in an already finished workflow shows Incomplete rather than implying that execution will resume. Short status hints explain these distinctions. These labels reflect the latest execution snapshot, rather than inferring readiness or a missed window from the browser clock.

One outer trading date controls the content. Daily Predictions directly shows the signal table; portfolio, performance and revision history remain accessible in the full task report. The signal table offers the same stock-pool families as backtests, defaults to the recorded strategy pool and Buyable only, and places the pool picker in the search toolbar. Pool rank and rank change use the selected pool; original ranks remain visible. Percentile membership uses eligible model candidates first, positive finite signal-time context, ceiling and code-order ties, independently per date/time. Showing blocked stocks never changes percentile membership. Missing context disables unavailable pools and explicitly explains an unavailable recorded pool. Inspecting a different pool does not recalculate or change published strategy results. Content omits the repeated model name and overall model status. Completed stage cards without metrics, files or explanations are omitted; running and failed stages remain visible. Child task details are accessed from the log toolbar. Published results omit successful calculation and publication stages. Search, pool selection, filtered row count and Buyable only share the table toolbar. Individual seed columns are replaced by one mean ± population standard deviation column with the same data bars as backtest tables (scaled over all candidate means, including zero); one seed has zero deviation and missing seeds have no deviation value. Non-mean aggregation retains the original ranking score and ranks stay unchanged. Missing-market assumptions appear as inline notes only in portfolio/performance views; incomplete evaluation warnings remain visible. Quality uses source tabs with one check table per source. Each check expands its issue samples inline without another table; complete stock evidence expands and loads on demand below the check table, with export support. Results default to the latest effective manifest revision, with a return action after inspecting older revisions. Stages and logs retain exact Task/Run ownership. Archived dates without execution records explicitly show diagnostics as unavailable, and missing signal dates never fall back to another date. Times use Asia/Shanghai. Refresh preserves the date, time, stage and model selection. Signal-history failures retain the last successful manifest with a warning.

Committed signal history is discovered from matching online inference Tasks even before the current run creates prediction children. Dates and submitted-signal counts include existing commits from earlier runs; execution stages and statuses still describe the current run. Multiple matching Tasks are reported as a history lookup failure rather than selecting an arbitrary result.

Offline backtests display their dedicated analytical report without the generic artifact count and file inventory. Artifact metadata remains available to report readers and files remain accessible in the workspace.

Cron schedulers atomically persist trigger state and bounded results under `workspace/schedules/<sha256-name>.json`: all active triggers and the latest 50 finished triggers. Results exceeding 16 KiB are represented by a truncated summary. Finished records survive service restart; unfinished records are marked cancelled with an interruption reason. Scheduler IDs remain process-specific. The schedule page displays last result metrics, errors, completion time and individual trigger details; scheduled Job success means the Job finished, while a submitted Task has its own lifecycle. Task records and artifacts keep their existing persistence semantics: a same-name rerun replaces the current Run.

Online reports show realtime collection, historical preparation and timed model inference. Comparison reports show shared downloads, per-model ETL, online-source checks, prediction differences and backtests. They share reporting components but have separate configured pages. Child details and selectable logs match both Task ID and exact Run ID; replaced runs cannot supply another invocation's results. Signal publication remains distinct from execution status.

Nightly comparison uses one navigation row: Workflow log, Data completion, Feature update, Offline prediction, Signal comparison and Backtest analysis. The model picker shares this row and preserves the current stage when switching models. The default view shows the parent workflow log; Data completion shows the nightly download task and its download descendants directly. Model stages show status, errors and exact owned task logs. Differing comparison checks appear before consistent checks. Backtest analysis embeds the existing backtest view and retains portfolio ledger comparison details. Artifact filenames link to workspace previews. Logs match both Task ID and Run ID, preserve selection on refresh and never substitute a replaced Run. Automatic refresh remains every 60 seconds alongside manual refresh.

Run `npm run dev:playground` and open `http://localhost:4173/AxonX/playground/#local/operations/online` for synthetic operations examples. The sync, data and nightly pages are independent examples; Playground resets on reload and does not demonstrate disk persistence or execute plugin algorithms.

When a referenced child Task runs again, its earlier Run metadata is unavailable through the current-status API. Online prediction groups these notices into one contextual message rather than asking users to refresh or treating the parent as replaced. Committed signal history remains independently readable, while newer child stages and logs are excluded. Other request and snapshot errors remain visible.

Quality checks with data and zero matched issues display “Passed”, including historical reports. Empty checks display “No data to check”; warning and filtering actions are shown only when issues are matched.

The three source tabs keep their existing navigation. Each uses four columns: check, result, description and issue samples, with warnings before passed checks. Checks without data appear only in the summary and are not counted as passed. Model input shows its own checks; upstream collection checks remain in their corresponding quote tabs and in the original full details.

Data updates show outcomes and meaningful progress on one page, including download child results. Counts, date ranges, failures and progress with counts or coverage are visible directly. Empty progress placeholders, duplicate child tables and internal stage cards are omitted. The toolbar keeps Data interfaces, Data results and Logs on the left and the task picker on the right. The whole-chain view collects interfaces and outcomes from exact owned child Runs even when the composite parent has no summary. Interfaces displays the deduplicated API list as formatted JSON, one API per line, alongside meaningful progress. Results displays each download task output as formatted JSON, omitting the API list already shown in Interfaces. JSON is visible directly without collapse controls or duplicate metric cards. Selecting a task switches all three views and exact owned Run logs together. Logs load on the first visit to Logs. Synchronization defaults to the latest execution and its result, while schedule configuration remains independently selectable. Deferred items are labeled “Not synced this round”, with “Items not synced this round” as the list heading: deferral can reflect batch limits or preparation/transfer errors. Rejected and oversized items receive explicit notices. An empty sync round differs from a missing result. Successful execution does not imply complete delivery. Exact Task/Run ownership, 60-second polling and manual refresh remain unchanged.

Synchronization executions use a single compact page with inline outcome counts and visible nonempty item lists. History rows show only time and state; outcomes and the complete persisted result JSON are displayed without collapsible sections.

Nightly feature refresh shows one compact summary followed by the selected model’s feature ETL log. A failed prerequisite takes precedence, and skipped downloads explain that existing raw data is reused.

Synchronization executions show finish time, duration, Job name, execution ID and scheduler ID inline. Duration is omitted for unfinished executions or invalid timestamps.

Nightly comparison contains workflow logs, data completion, feature refresh, offline prediction and prediction comparison. It has no backtest stage or report link; historical performance is evaluated independently in offline research. Old compare Runs keep their archived backtest artifacts.

Prediction comparison uses code-aligned Top 5/10/20/30/50 lists with paired online/offline ranks, scores and raw-seed population STD. Click a stock for seed details, switch between strategy-buyable and all-model rankings, or filter differences. Logs are omitted. Difference diagnostics are expanded by default and difference files remain accessible. Missing older artifacts, invalid data and loading errors are explicit.

Top N and stock-pool dropdowns filter online and offline lists together. Code and name use separate compact columns; overlap is shown beside the filters. Diagnostics open by default with stage summaries, sample/schema coverage and scrollable differing fields.

Top N and stock-pool filters reuse the model picker’s accessible in-page dropdown, including keyboard navigation and selected markers. They sit on the right of the table’s search toolbar; one compact outcome/date/coverage/overlap row precedes the table, with scoring details in its tooltip.
