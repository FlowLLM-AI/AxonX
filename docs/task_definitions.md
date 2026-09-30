# Task definition queries

Use the plugin list to find a plugin Task registration name:

```bash
axonx plugin list --target <host:port>
```

Confirm that the selected plugin's `error` is null, then select a key from its
`tasks` mapping as the `--task` value. The mapping values are Python class
references, not registration names. A manifest declaration does not guarantee
that the Task can load or execute.

Query the selected Task's description, type, and input/output schemas:

```bash
axonx get_task_definition --task a158_etl --target <host:port>
```

`--task` is the registration name, not a Task ID or the instance name supplied
through `--task-name`. Use the same target service for discovery, definition
queries, and submission. Without `--target`, `plugin list` reads the CLI's
Python environment, while definition queries and submission connect to the
local AxonX service; these may use different Python environments.

To browse all built-in and plugin Task definitions, use:

```bash
axonx list_installed_task_definitions --target <host:port>
```

Studio uses this full list to populate its submission form.

## HTTP API

The new command invokes `POST /jobs/get_task_definition` with this request body:

```json
{"arguments": {"task": "a158_etl"}}
```

The response envelope's `answer` is one definition object with `name`, `source`,
`plugin`, `task_type`, `description`, `input_schema`, and `output_schema`. It has
the same structure as an item returned by `list_installed_task_definitions`.
Default jobs require the target service's configured bearer token; pass it with
`--token` when using the CLI.

## Resolution behavior

Single queries, list queries, submission, and local execution share the same
registration catalog. Single queries load only the requested Task; list queries
load every Task and can fail if any Task cannot be loaded. Unknown registration
names fail with an error listing known names.

Plugin registration names that collide with built-in Task names are now rejected.
Previously, lists could expose the plugin class while submission selected the
built-in class. Rename conflicting plugin registrations before using the shared
catalog. Duplicate names across plugin distributions remain errors.
