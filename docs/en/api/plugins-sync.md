# Plugin Commands and Synchronization API

Plugin management runs through the ordinary `cli` Job; synchronization retains dedicated Jobs.

Use the [HTTP/MCP protocol](overview.md) and discover schemas with `axonx help --job NAME`. Replace example Task/session IDs with actual values.

## Endpoint list

| Job          | Purpose                                                  |
| ------------ | -------------------------------------------------------- |
| `sync_index` | Read committed file inventories for one source.          |
| `sync_files` | Commit a staged file batch without parsing its contents. |

## sync_index

Read committed file inventories for one synchronization source.

| Argument | Type     | Required | Constraints                                   |
| -------- | -------- | -------- | --------------------------------------------- |
| `source` | `string` | yes      | 1–128 letters, digits, underscores or hyphens |

```json
{
  "arguments": {
    "source": "SOURCE_ID"
  }
}
```

Returns `transfer_budget_bytes` and `groups`. Each group contains an opaque `version`, an ordered integer `revision`, and `directories`: workspace-relative directories mapped to relative filenames and `{size, revision}` records. Receipts live in `sync/receipts/SOURCE_ID.json`. The index checks each installed directory once and returns the latest file inventory for shared directories, so normal shared updates do not cause repeated transfers. Missing files make affected groups eligible for retransmission. It does not parse Task metadata or build the Task index.

The sender derives its stable source ID from its hostname and workspace path. Source selection, model patterns and publication policy remain on the sender.

## sync_files

Commit a staged file batch without interpreting its contents.

| Argument | Type     | Required | Constraints                            |
| -------- | -------- | -------- | -------------------------------------- |
| `path`   | `string` | yes      | Workspace-relative staged archive path |

```json
{
  "arguments": {
    "path": "tmp/uploads/ACTUAL_UPLOAD_PATH/archive.tar.gz"
  }
}
```

## File manifest

The gzip tar archive contains `sync-manifest.json` and changed regular-file payloads. Its manifest has this shape:

```json
{
  "source": "SOURCE_ID",
  "groups": {
    "report": {
      "version": "source-publication-version",
      "revision": 1,
      "directories": {
        "tasks/base/base#demo#report": {
          "metadata.json": { "size": 123, "revision": "opaque-file-version" }
        }
      }
    }
  }
}
```

Each group declares its complete desired directory inventory, including unchanged files omitted from the payload. Destinations have the workspace layout `tasks/TYPE/DIRECTORY` or `tmp/tasks/TYPE/DIRECTORY`. The receiver reuses files only when their receipt matches, checks paths, sizes and compressed/reconstructed budgets, and commits directories and receipts together with rollback on failure. Repeated identical batches are accepted; stale or conflicting revisions are rejected, including shared-directory regressions.

A new inventory removes obsolete directories owned solely by that group. Empty `directories` removes the group's files and retains its revision as a tombstone. Other groups' directories and existing unowned directories are preserved. File revisions are opaque identifiers, not content checksums.

Returns `archive`, `applied`, `deleted` and `files`, then removes the staged upload. The existing `task_index` scanner discovers supported `metadata.json` records after publication; file transfer does not depend on that schema. Display replicas remain read-only and cannot serve as research inputs.

## Plugin commands

Call `cli` with argv `["plugin", "list"]`, `["plugin", "show", "DISTRIBUTION"]`, `["plugin", "install", "/absolute/upload/location.whl"]`, or `["plugin", "uninstall", "DISTRIBUTION"]`. The response contains process stdout/stderr, exit_code and truncation flags. Plugin metadata is JSON in stdout. There are no dedicated plugin-management Jobs or automatic live-catalog refresh. Install local wheels with the explicit [deployment flow](../plugins/management.md); upload uses `/upload`.

## Visibility of sync_flush

The default configuration leaves `sync_flush` commented out because it requires a configured sync component. Expose it as a pipeline Job with `backend: sync_flush_step` only when that component exists. Invoke it manually or from a custom host workflow; Cron supports Task exec commands. See [Task synchronization](../guides/task-sync.md).

Source: [Default Job contracts](../../../axonx/app/config/default.yaml) · [Job protocol](overview.md)
