# Plugin Installation and Deployment

Plugins are Python distributions that register Tasks through `axonx.plugins` entry points and `plugin.yaml`. Management commands modify the Python environment in which they execute.

![Plugin deployment](../../figures/guides/plugin-deployment.svg)

## Three names

| Name              | Purpose                                                   |
| ----------------- | --------------------------------------------------------- |
| Distribution      | pip installation and uninstallation; `project.name`       |
| Plugin entry name | Identifies an `axonx.plugins` entry pointing to a package |
| Task registration | Key in `plugin.yaml.tasks`; used by `exec --task`         |

Query the actual registration name before executing. Package names and Task names are not interchangeable.

## Inspect the current environment

```bash
axonx plugin list
axonx plugin show DISTRIBUTION
axonx plugin inspect DISTRIBUTION
```

Local commands inspect the current interpreter. Add `--target HOST:PORT` to run the command in the service's interpreter. Each command starts a new process and discovers installed metadata.

## Prepare plugin sources

Research plugins are not published to PyPI. Clone this repository and install them in dependency order: Alpha158 → factor → strategy. pip resolves declared dependencies but does not locate sibling source directories automatically. An unmet research dependency may cause pip to search the configured package index.

## Build and inspect from source

```bash
axonx plugin build ./plugins/qlib_a158 --output ./dist/plugins
axonx plugin inspect './dist/plugins/ACTUAL_FILENAME.whl'
```

Build output includes `wheel`, `sha256`, `content_sha256`, distribution, version, requirements and registrations. Save the actual wheel filename. Without `--output`, builds use `.axonx/plugins/artifacts/<source fingerprint>` relative to the CLI working directory. Existing wheels cannot be combined with `--output`. Source hashing ignores environments/caches and rejects symlinks in included source.

## Local installation

```bash
axonx plugin install -e ./plugins/qlib_a158
axonx plugin install -e ./plugins/qlib_factor
axonx plugin install -e ./plugins/qlib_strategy
```

Editable installs still build and validate a wheel first; they require a source directory and reject `--output`. Ordinary `plugin install PATH` installs the built or supplied wheel. The installer installs declared dependencies except AxonX itself, force-reinstalls the plugin without dependencies, and validates installed provenance/content. Ensure the current AxonX version meets the plugin requirement.

## Deploy remotely

A target forwards the command; it does not transfer local files. `plugin install ./source --target HOST:PORT` interprets `./source` in the target service's workspace. When starting with local source, perform all of these steps:

1. Build a wheel locally.
2. Upload that wheel to the destination service's `POST /upload` endpoint.
3. Install the upload's absolute `location` through the same service's `cli` Job.
4. Clean up the upload using its workspace-relative `path`.
5. Restart the persistent service to refresh its Task catalog and verify definitions.

The following script runs after local wheel construction; replace the filename, service address and token. It validates installation and cleans up on success or failure:

```python
import asyncio
import hashlib
import json
import os
from pathlib import Path
from axonx.client.http import HttpClient

async def deploy():
    wheel = Path("dist/plugins/ACTUAL_FILENAME.whl")
    expected_sha256 = hashlib.sha256(wheel.read_bytes()).hexdigest()
    async with HttpClient(
        target="http://research.example:1024",
        token=os.environ["AXONX_TARGET_TOKEN"],
        timeout=600.0,
    ) as client:
        uploaded = await client.copy_file(wheel)
        try:
            response = await client.run_job("cli", {
                "argv": ["plugin", "install", uploaded.location],
            })
            result = response.answer
            if not response.success or result["exit_code"] != 0:
                raise RuntimeError(str(result))
            installed = json.loads(result["stdout"])
            if installed["sha256"] != expected_sha256:
                raise RuntimeError("Installed wheel differs from local wheel")
            print(installed)
        finally:
            await client.discard_file(uploaded.path)

asyncio.run(deploy())
```

The explicit local hash comparison verifies the installed wheel against the local artifact after installation. The CLI does not accept a caller-provided expected hash. The installer separately verifies installed provenance against the wheel read on the target. Cleanup does not roll back an installation. Interrupted or timed-out installation requests require checking the target environment before retrying; pip may already have changed files.

If using curl, upload with `-F 'file=@LOCAL.whl'` to `/upload`, then run `axonx plugin install '<answer.location>' --target HOST:PORT --client-timeout 600`. Use `DELETE /upload?path=<answer.path>` for cleanup. Set `AXONX_TARGET_TOKEN` for CLI authentication. Keep upload, install, cleanup and queries on the same service.

`location` is an absolute path for target-side installation; `path` is relative to the remote workspace and is used for upload cleanup. A local source path cannot stand in for either. A wheel or source tree already present on the target can be installed directly. Remote editable installs refer to source already on that machine.

## Checksums and restart

`sha256` identifies wheel bytes; `content_sha256` identifies normalized plugin content. They are different hashes. Installation results have no restart flag and do not refresh loaded service modules. New `exec` and `plugin` processes discover installed plugins; persistent definition Jobs and Studio use the startup catalog and cached classes. Restart the service after changing registrations, schemas or loaded dependencies:

```bash
axonx restart_service --target research.example:1024
# After the service is reachable again:
axonx plugin list --target research.example:1024
axonx list_task_defs --target research.example:1024
axonx get_task_def --task qlib_a158_etl --target research.example:1024
```

A successful restart response means acceptance; inspect `get_update_status` for completion. Coordinate installations yourself: plugin environment mutations are not serialized, and existing processes are not version-isolated.

## Uninstallation and troubleshooting

```bash
axonx plugin uninstall DISTRIBUTION --target research.example:1024
```

Uninstallation removes installed code, not historical artifacts. Restart persistent services to refresh their catalogs. For failures, distinguish local file paths, remote `location`, remote `path`, target interpreter, dependency availability and Task registration names. Follow the returned error and process exit code.

[Plugin manifest](../reference/plugin-manifest.md) · [File upload and cleanup](../api/workspace.md) · [Development guide](../dev_guide.md)

Sources: [CLI](../../../axonx/cli/commands.py), [installer](../../../axonx/plugin/installer.py), [HTTP client](../../../axonx/client/http.py).

## Research plugins

[Alpha158](../../../plugins/qlib_a158/README.md) · [Qlib Factor](../../../plugins/qlib_factor/README.md) · [Qlib Strategy](../../../plugins/qlib_strategy/README.md)
