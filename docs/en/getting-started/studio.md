# Studio

Open Playground from the website to inspect fictional Task records, research results, workspace files and scripted Agent sessions without a service. Playground provides read-only Task definitions and records; it does not launch or cancel Tasks. Refresh or Reset demo restores its synthetic state.

## Connect a service

Install `axonx[studio]`, configure a service token and start `axonx start`. Open `http://127.0.0.1:1024` and configure its connection token in Studio settings. The service and independently launched CLI Tasks must share workspace and log paths for observation.

Machine selection controls Task lists, definitions, logs, research results and workspace queries. Requests use the selected target and preserve same-origin authentication. Task execution uses CLI exec on the execution machine.

## Task definitions

The Task definitions page groups installed Tasks by plugin and supports search. Selecting a Task shows its description and input/output JSON schemas. It contains no execution form or submit action.

## Task records

All tasks groups records by type and registration. Search and type/state filters apply to records; expanded groups show 50 rows per page. Copy IDs or open details to inspect configuration, relationships, steps, children and logs. The list and detail pages have no Task cancellation, deletion or multiselect controls.

Task observation refreshes through the shared 60-second scheduler and supports manual refresh. Changing machine or Task aborts obsolete requests. Status comes from the last published metadata; service restart does not repair or terminate independent local exec processes.

## Research, files and tools

Research pages read successful Task artifacts. Strategy comparison calculates metrics on aligned backtest dates without executing new Tasks. Workspace browsing, preview and generic file deletion remain available; replica synchronization also remains separate from Task lifecycle management.

Agent sessions support conversation, session management and interruption of a turn. Stopping a turn does not control independent Tasks. API interfaces expose the selected service's Job catalog; Task APIs provide definition and observation queries. Remote CLI remains a separate capability and its command process follows that request's lifecycle.

[Execute and observe Tasks](../guides/task-management.md) · [Research results](../research/results.md) · [Workspace files](../guides/workspace-files.md)
