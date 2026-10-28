# Workspace Files

## Browse directories

```bash
axonx list_entries --path ''
axonx list_task_directories --task-type base
axonx preview_file --path 'base/base#demo#check/metadata.json' --max-bytes 8192
```

Paths are relative to the selected service workspace. list_entries uses offset pagination and bounded listings. list_task_directories selects type directories containing metadata.json, regardless of current lifecycle state. The Task ID includes # and should be shell-quoted.

## Preview records and artifacts

Use paths from current metadata.output_params.artifacts and resolve them inside the Task directory. Preview text, Markdown, JSON/YAML, CSV, JSONL and Parquet through preview_file. Structured previews and row pages have format-specific fields; inspect parse errors, truncation, row_count and has_more rather than assuming every file returns the same shape.

## Formats and limits

`max_bytes` controls text, Markdown, JSON and YAML previews (up to 32 MiB); `offset` and `limit` page row formats, with at most 5000 rows. JSONL has its own 512 KiB page budget; `max_bytes` does not change it. CLI defaults are 20 rows/8192 bytes. JSONL retains malformed/incomplete lines with raw content and parse_error; valid rows include parsed data. A bounded preview is not a full artifact or a research-quality acceptance check.

## Clean up files and directories

Use delete_entries with a JSON paths array. This general file capability has no active-Task process protection. Stop writers, check source identity and serialize against execution before deleting current Task directories. Deletion removes persistent/ too; it does not terminate a process or rebuild downstream outputs.

## Upload and subsequent consumption

POST /upload or HttpClient.copy_file stages one file under tmp. StagedFile contains path, size and absolute location. Install a target-side plugin using location; sync and cleanup use relative path. Uploading does not install anything, and plugin installation does not delete the upload automatically. Clean up in finally; see [Upload API](../api/workspace.md).

## Troubleshooting

Confirm target, workspace root, exact relative path, response bounds and replica sampling/omissions. Research pages require standard metadata/artifact contracts, not just files with familiar names.

Sources: [Workspace](../../../axonx/app/workspace/core.py), [previews](../../../axonx/app/workspace/preview.py), [uploads](../../../axonx/app/workspace/uploads.py).
