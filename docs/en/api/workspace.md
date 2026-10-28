# Workspace and Upload API

File Jobs operate on the selected workspace. Artifact paths come from current Task metadata.

All Jobs below use `POST /jobs/NAME` with `{"arguments": {...}}`. Streams use `/jobs/NAME/events`; MCP uses the same Job name and business arguments. Discover the target schema with `help --job NAME`. Replace example Task/session IDs with actual values.

![Upload, consume and clean up](../../figures/api/upload.svg)

## Endpoint list

| Job                     | Purpose                                                               |
| ----------------------- | --------------------------------------------------------------------- |
| `list_entries`          | List one directory inside the configured workspace.                   |
| `list_task_directories` | List Task directories containing metadata.json.                       |
| `preview_file`          | Preview one supported file inside the configured workspace.           |
| `delete_entries`        | Delete multiple files or directories inside the configured workspace. |

## list_entries

List one directory inside the configured workspace.

| Argument | Type      | Required | Default / constraints       |
| -------- | --------- | -------- | --------------------------- |
| `path`   | `string`  | no       | `{"default":""}`            |
| `offset` | `integer` | no       | `{"minimum":0,"default":0}` |

```json
{
  "arguments": {
    "path": ""
  }
}
```

`answer` contains `path`, absolute `workspace_root`, `entries` and `truncated`. Entries are sorted directory-first, then by case-insensitive name and exact name, with at most 5000 entries after `offset`. Continue with `offset + entries.length` when truncated. Entries expose name, relative path, kind, preview_kind, supported, size and modified_at; symlinks may be listed but cannot be traversed.

## list_task_directories

List Task directories containing metadata.json.

| Argument    | Type     | Required | Default / constraints                                     |
| ----------- | -------- | -------- | --------------------------------------------------------- |
| `task_type` | `string` | yes      | `{"minLength":1,"pattern":"^[A-Za-z0-9][A-Za-z0-9_-]*$"}` |

```json
{
  "arguments": {
    "task_type": "base"
  }
}
```

Lists directories of the selected task_type that contain metadata.json. This is file discovery, not an immutable execution history.

## preview_file

Preview one supported file inside the configured workspace.

| Argument    | Type      | Required | Default / constraints                        |
| ----------- | --------- | -------- | -------------------------------------------- |
| `max_bytes` | `integer` | no       | `{"minimum":1,"maximum":33554432}`           |
| `path`      | `string`  | yes      | `—`                                          |
| `offset`    | `integer` | no       | `{"minimum":0,"default":0}`                  |
| `limit`     | `integer` | no       | `{"minimum":1,"maximum":5000,"default":200}` |

```json
{
  "arguments": {
    "path": "base/base#demo#api-check/metadata.json",
    "limit": 20,
    "max_bytes": 8192
  }
}
```

## delete_entries

Delete multiple files or directories inside the configured workspace.

| Argument | Type    | Required | Default / constraints           |
| -------- | ------- | -------- | ------------------------------- |
| `paths`  | `array` | yes      | `{"minItems":1,"maxItems":200}` |

```json
{
  "arguments": {
    "paths": ["base/base#demo#api-check"]
  }
}
```

Deletes workspace-relative paths. It is a general file operation without active-Task process protection. Verify the Task is stopped and serialize against execution before deleting a directory.

## File upload and cleanup

`POST /upload` accepts a raw binary body with `x-file-name`, or multipart fields `file` and optional `directory`. Optional `x-file-directory` overrides the multipart directory. The destination is confined to workspace `tmp`; a UUID directory avoids collisions. The transfer budget defaults to 512 MiB, with 64 KiB extra multipart framing.

```bash
curl --fail-with-body 'http://HOST:1024/upload' \
  -H "Authorization: Bearer $AXONX_TARGET_TOKEN" \
  -F 'file=@dist/plugins/ACTUAL_FILENAME.whl'
```

The JobResponse answer is `StagedFile`: `{ "path": "tmp/UUID/file.whl", "location": "/absolute/workspace/tmp/UUID/file.whl", "size": 123 }`. Use location for target-side native plugin installation, path for `sync_tasks` or `DELETE /upload?path=...`. Both routes use the same service token. Uploading does not install or execute the file. Plugin installation does not automatically consume/delete the upload; clean it in a finally block. Expiry cleanup is opportunistic on later uploads (default retention seven days), not an immediate install cleanup.

## Preview response types

All preview variants include `kind` and byte `size`. Limits depend on the format:

| Format         | Response fields and limits                                                                                                                               |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Text           | `content`, `truncated`; default prefix 512 KiB, overridden by `max_bytes`                                                                                |
| Markdown       | Body `content`, parsed `frontmatter`, `frontmatter_error`, `truncated`; same prefix budget as text                                                       |
| JSON / YAML    | Parsed `data` or source `content` with `parse_error`; without `max_bytes`, parse up to 32 MiB and return an error for larger files                       |
| CSV            | `columns`, row arrays, `offset`, `limit`, `has_more`; header excluded from row offset                                                                    |
| JSONL / NDJSON | `rows` with line, content, data, parse_error and per-row truncated; 512 KiB page budget independent of `max_bytes`, plus page `truncated` and `has_more` |
| Parquet        | `columns`, `column_schema`, row arrays, `row_count`, `row_group_count`, `offset`, `limit`, `has_more`                                                    |
| Unsupported    | `kind="unsupported"`, `size`; no payload preview                                                                                                         |

Row formats default to 200 rows per page, up to 5000. `max_bytes` applies only to text, Markdown, JSON and YAML and accepts at most 32 MiB. Partial JSON/YAML returns a marked source prefix and a parse error rather than a parsed object. CLI adds defaults of 20 rows and 8192 bytes; ordinary HTTP/MCP Job calls use the server defaults above. Use `has_more` for row pagination and inspect replica sampling/omissions before treating a preview as full evidence.

Source: [Default Job contracts](../../../axonx/app/config/default.yaml) · [Job protocol](overview.md)
