# Workspace and Upload API

File Jobs operate on the selected workspace. Artifact paths come from current Task metadata.

Use the [HTTP/MCP protocol](overview.md) and discover schemas with `axonx help --job NAME`. Replace example Task/session IDs with actual values.

## Endpoint list

| Job              | Purpose                                                               |
| ---------------- | --------------------------------------------------------------------- |
| `list_entries`   | List one directory inside the configured workspace.                   |
| `preview_file`   | Preview one supported file inside the configured workspace.           |
| `delete_entries` | Delete multiple files or directories inside the configured workspace. |

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

## preview_file

Preview one supported file inside the configured workspace.

| Argument        | Type      | Required | Default / constraints                        |
| --------------- | --------- | -------- | -------------------------------------------- |
| `allow_missing` | `boolean` | no       | `{"default":false}`                          |
| `max_bytes`     | `integer` | no       | `{"minimum":1,"maximum":33554432}`           |
| `path`          | `string`  | yes      | `—`                                          |
| `offset`        | `integer` | no       | `{"minimum":0,"default":0}`                  |
| `limit`         | `integer` | no       | `{"minimum":1,"maximum":5000,"default":200}` |

```json
{
  "arguments": {
    "path": "tasks/base/base#demo#api-check/metadata.json",
    "limit": 20,
    "max_bytes": 8192
  }
}
```

Set `allow_missing: true` for a file that has not been produced yet: an absent file returns a successful `answer: null`. The default treats absence as an error. Invalid paths, permission failures and malformed file contents retain their normal error or `parse_error` behavior.

## delete_entries

Delete multiple files or directories inside the configured workspace.

| Argument | Type    | Required | Default / constraints           |
| -------- | ------- | -------- | ------------------------------- |
| `paths`  | `array` | yes      | `{"minItems":1,"maxItems":200}` |

```json
{
  "arguments": {
    "paths": ["tasks/base/base#demo#api-check"]
  }
}
```

Deletes workspace-relative paths. It is a general file operation without active-Task process protection. Verify the Task is stopped and serialize against execution before deleting a directory.

## File upload and cleanup

`POST /upload` accepts a raw binary body with `x-file-name`, or multipart fields `file` and optional `directory`. Optional `x-file-directory` overrides the multipart directory. The destination is confined to workspace `tmp`; a UUID directory avoids collisions. The transfer budget defaults to 512 MiB, with 64 KiB extra multipart framing.

The CLI sends a local file through this endpoint:

```bash
axonx upload --path dist/plugins/ACTUAL_FILENAME.whl --target HOST:1024
```

The equivalent multipart request is:

```bash
curl --fail-with-body 'http://HOST:1024/upload' \
  -H "Authorization: Bearer $AXONX_TARGET_TOKEN" \
  -F 'file=@dist/plugins/ACTUAL_FILENAME.whl'
```

The JobResponse answer is `StagedFile`: `{ "path": "tmp/uploads/UUID/file.whl", "location": "/absolute/workspace/tmp/uploads/UUID/file.whl", "size": 123 }`. Use location for target-side native plugin installation, path for `DELETE /upload?path=...`. Both routes use the same service token. Uploading does not install or execute the file. Plugin installation does not automatically consume/delete the upload; clean it in a finally block. Expiry cleanup is opportunistic on later uploads (default retention seven days), not an immediate install cleanup.

The CLI uses the returned workspace-relative path for cleanup:

```bash
axonx discard_file --path tmp/uploads/UUID/file.whl --target HOST:1024
```

## Directory replacement

`POST /upload?mode=replace` accepts a gzip tar archive through the same binary or multipart upload formats. The default `mode=stage` retains the ordinary staged-file behavior.

```bash
axonx upload_archive --path ./files.tar.gz --target HOST:1024
```

The archive starts with `directories.json`, a JSON array of nonoverlapping workspace-relative destination directories, followed by all regular files under those paths. For example, `["reports/daily"]` declares a complete replacement of `reports/daily/`. Empty listed directories are supported. Symlinks, traversal paths, duplicate members, overlapping roots and destinations covering upload or file-transfer staging are rejected.

The request and complete expanded tar stream, including extension headers and padding, must each fit `transfer_budget_bytes`. The receiver extracts into temporary storage, replaces the listed directories and rolls back installation failures. Existing files missing from a replacement directory are removed; unlisted directories remain untouched. Files are opaque and are not executed or interpreted. Concurrent readers can observe directories being replaced; a multi-directory batch is not a reader transaction.

The answer is the replaced directory list, for example `["reports/daily"]`. Uploaded archives and operation staging are cleaned after completion or a successful rollback. If rollback itself fails, original directories are retained under the staging backup path reported by the error for recovery. Python callers can build an archive with `axonx.client.files.build_file_archive` and send it with `HttpClient.upload_archive`.

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

Row formats default to 200 rows per page, up to 5000. `max_bytes` applies only to text, Markdown, JSON and YAML and accepts at most 32 MiB. Partial JSON/YAML returns a marked source prefix and a parse error rather than a parsed object. CLI adds defaults of 20 rows and 8192 bytes; ordinary HTTP/MCP Job calls use the server defaults above. Use `has_more` for row pagination and inspect the complete source before treating a preview as full evidence.

Source: [Default Job contracts](../../../axonx/app/config/default.yaml) · [Job protocol](overview.md)
