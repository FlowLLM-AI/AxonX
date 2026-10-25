# Plugin and synchronization interfaces

Plugin management uses Plugin CLI through the generic service `cli` gateway. The dedicated list_plugins, inspect_plugin, install_plugin and uninstall_plugin Jobs are removed.

```bash
axonx plugin list --target '<host:port>'
axonx plugin install '<location returned by upload>' --target '<host:port>'
```

HTTP callers use `POST /jobs/cli` with `{"argv": ["plugin", "list"]}`. The result contains stdout, stderr, exit_code and truncation flags. Upload, installation and upload cleanup remain separate. Paths belong to the target machine; clean uploaded files with `DELETE /upload?path=...`. There is no staged-install cleanup bypass. Plugin validation, build and installation belong to `plugin`.

See [Plugin management](../plugins/management.md) and [Job conventions](overview.md).

## sync_tasks

Receive a verified display-replica archive and replace directories, or apply deletions only.

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

The receiver validates directory identity and archive paths, retaining rollback support when applying replacements. The transfer consists of display replicas with selected published outputs; it does not migrate processes, plugin environments, Agent sessions, upstream inputs, or raw data trees.

## task_sync_index

Accepts optional `task_names` and `live_task_ids`. Returns `answer.transfer_budget_bytes`, one `answer.tasks` index (source/policy revisions, Run IDs and replica file records). `sync_tasks` accepts terminal replicas or complete live groups with a full manifest and verified delta bases. Unmarked source archives are rejected. Native active Tasks cannot be overwritten; live replicas accept newer snapshots from the same source. The sender reconciles ordinary Tasks on its first flush and captures live groups on each flush. Deletions are not propagated automatically. See [Result display synchronization](../guides/task-sync.md).

## Visibility of sync_flush

sync_flush is commented out by default in default.yaml; enable_serve=false in the enabling example restricts it to internal scheduling. It is not a default public API and cannot be assumed to appear in /jobs. SyncReport contains uploaded, rejected, oversized, deferred, and archives; see [Task synchronization](../guides/task-sync.md).

## Related documentation

- [Protocol, authentication, and errors](overview.md)
- [Plugin management](../plugins/management.md)
- [CLI reference](../reference/cli.md)
- [Event protocol](events.md)

Implementation references: `axonx/app/config/default.yaml`, `axonx/cli/plugin.py` and `axonx/app/components/service/http/jobs.py`.
