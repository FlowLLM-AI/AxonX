# Plugin and sync API

These endpoints change the service's Python environment or workspace Task directories. Upload files to staging first, then pass the returned path to the corresponding consumer.

![Plugin and sync API call flow](../../figures/api/upload.svg)

## Calling conventions

All endpoints below use `POST /jobs/{name}` with a `{"arguments":{...}}` request body. For remote forwarding, add `target` at the envelope's top level, outside arguments. Every response uses [JobResponse](overview.md#responses-and-errors). Table defaults come from the current built-in configuration and Steps. Deployments may change Job Schemas; the running service's `/jobs` is authoritative.

All JSON examples illustrate structure; replace task IDs, session IDs, file paths, and hashes with values actually returned by your service. See [Task contracts](../reference/task-contracts.md) for the complete shared TaskStatus fields.

## Endpoint list

| Job                | Purpose                                                                  |
| ------------------ | ------------------------------------------------------------------------ |
| `list_plugins`     | Inspect all AxonX plugins in the service's Python environment.           |
| `inspect_plugin`   | Inspect an installed plugin.                                             |
| `install_plugin`   | Install an uploaded and verified wheel.                                  |
| `uninstall_plugin` | Uninstall a plugin distribution from the service environment.            |
| `sync_tasks`       | Receive a task archive and replace directories, or apply deletions only. |

## list_plugins

Inspect all AxonX plugins in the service's Python environment.

No public business parameters; use `{"arguments":{}}`.

**Request**

```json
{
  "arguments": {}
}
```

**Response**

answer is an array of PluginInfo: distribution, version, plugins, tasks, components, jobs, requirements, content_sha256, sha256, and error.

```json
{
  "answer": [],
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

A nonempty error indicates discovery or parsing problems; not every installed Python package is an AxonX plugin.

## inspect_plugin

Inspect an installed plugin.

| Parameter | Type   | Required | Default       | Constraints and meaning                                   |
| --------- | ------ | -------- | ------------- | --------------------------------------------------------- |
| `plugin`  | string | Yes      | `— (omitted)` | Distribution name or plugin entry-point name; minLength=1 |

The Schema does not prohibit extra fields; this does not mean those fields will be used.

**Request**

```json
{
  "arguments": {
    "plugin": "axonx-example"
  }
}
```

**Response**

answer is a single PluginInfo with the same structure as each list_plugins item.

```json
{
  "answer": {
    "distribution": "axonx-example",
    "version": "0.1.0",
    "plugins": ["example"],
    "tasks": {},
    "components": {},
    "jobs": {},
    "requirements": [],
    "content_sha256": null,
    "sha256": null,
    "error": null
  },
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

Unknown or ambiguous plugin names return failure. Distinguish distribution names, entry-point names, and Task registration names.

## install_plugin

Install an uploaded and verified wheel.

| Parameter | Type   | Required | Default       | Constraints and meaning                               |
| --------- | ------ | -------- | ------------- | ----------------------------------------------------- |
| `path`    | string | Yes      | `— (omitted)` | Path relative to the service workspace; minLength=1   |
| `sha256`  | string | Yes      | `— (omitted)` | SHA-256 returned by upload; regex `^[0-9a-fA-F]{64}$` |

Only the business fields listed in the table are accepted.

**Request**

```json
{
  "arguments": {
    "path": "tmp/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/axonx_example-0.1.0-py3-none-any.whl",
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
}
```

**Response**

answer is PluginInstallResult, which adds restart_required to PluginInfo.

```json
{
  "answer": {
    "distribution": "axonx-example",
    "version": "0.1.0",
    "plugins": ["example"],
    "tasks": {},
    "components": {},
    "jobs": {},
    "requirements": [],
    "content_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "error": null,
    "restart_required": true
  },
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

The example hash and path only illustrate their formats; replace them with values returned by POST /files. Verification applies to the staged wheel; a local source directory cannot be passed. Cleanup of the staged file is attempted on both success and failure. Restart after installation changes to reassemble contributions.

## uninstall_plugin

Uninstall a plugin distribution from the service environment.

| Parameter | Type   | Required | Default       | Constraints and meaning                                   |
| --------- | ------ | -------- | ------------- | --------------------------------------------------------- |
| `plugin`  | string | Yes      | `— (omitted)` | Distribution name or plugin entry-point name; minLength=1 |

Only the business fields listed in the table are accepted.

**Request**

```json
{
  "arguments": {
    "plugin": "axonx-example"
  }
}
```

**Response**

answer is PluginUninstallResult: distribution and restart_required.

```json
{
  "answer": {
    "distribution": "axonx-example",
    "restart_required": true
  },
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

Uninstalling does not immediately remove in-memory contributions from a running Application; follow the restart instructions.

## sync_tasks

Receive a task archive and replace directories, or apply deletions only.

| Parameter   | Type   | Required | Default       | Constraints and meaning                             |
| ----------- | ------ | -------- | ------------- | --------------------------------------------------- |
| `path`      | string | No       | `— (omitted)` | Path relative to the service workspace; minLength=1 |
| `deletions` | array  | No       | `[]`          | Task directory paths to delete; maxItems=200        |

Only the business fields listed in the table are accepted.

**Request**

```json
{
  "arguments": {
    "deletions": []
  }
}
```

**Response**

answer is SyncTasksReport: archive, applied, deleted, and files.

```json
{
  "answer": {
    "archive": null,
    "applied": [],
    "deleted": [],
    "files": 0
  },
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

path is optional. deletions defaults to [] and allows at most 200 entries. path accepts only an uploaded staged archive; deletions contains type/Task ID task directories, rather than arbitrary file paths. A receive failure sets success=false and returns error text in answer; the archive is subsequently cleaned up.

## Failure response examples

Submitting an invalid sha256 format for installation returns HTTP 422. If the format is valid but the artifact does not match the hash, the installation consumer fails verification and cleans up the staged file. Upload again before retrying.

sync_tasks directly returns business-failure text for OSError, TypeError, or ValueError involving staging paths/archives, for example when a staged file is missing:

```json
{ "answer": "Staged file does not exist", "success": false, "metadata": {} }
```

The receiver validates directory identity and archive paths, retaining rollback support when applying replacements. The transfer consists of snapshots of terminal task directories; it does not migrate processes, plugin environments, Agent sessions, or raw data trees.

## Visibility of sync_flush

sync_flush is commented out by default in default.yaml; enable_serve=false in the enabling example restricts it to internal scheduling. It is not a default public API and cannot be assumed to appear in /jobs. SyncReport contains uploaded, deleted, rejected, oversized, deferred, and archives; see [Task synchronization](../guides/task-sync.md).

## Related documentation

- [Protocol, authentication, and errors](overview.md)
- [Plugin management](../plugins/management.md)
- [CLI reference](../reference/cli.md)
- [Event protocol](events.md)

Implementation references: `axonx/config/default.yaml`, `axonx/steps/plugin/` and `axonx/components/service/http/jobs.py`.
