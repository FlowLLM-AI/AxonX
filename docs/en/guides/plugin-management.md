# Plugin installation and deployment

Plugins are Python packages providing AxonX Tasks, Components, and Jobs. Local management commands operate on the current Python environment; only an explicit `--target` operates on a remote service. Building and installation read plugin code and dependencies, and the service usually needs restarting afterward to reassemble contributions.

![Plugin deployment workflow](../../figures/guides/plugin-deployment.svg)

## Three names

| Name                 | Purpose                                        | Source                         |
| -------------------- | ---------------------------------------------- | ------------------------------ |
| distribution         | Python package installation and uninstallation | project.name in pyproject.toml |
| plugin name          | Discover and distinguish plugin entries        | axonx.plugins entry point      |
| Task registered name | submit / exec / definition queries             | tasks in plugin.yaml           |

These three names may differ. Do not pass a distribution name directly to `--task`; first check the Task registered names in plugin contributions.

## Inspect the current environment

```bash
axonx plugin list
axonx plugin show '<distribution or plugin name>'
axonx plugin inspect '<distribution or plugin name>'
```

Displayed fields include distribution, version, entry name, requirements, and contributions. Query the definition interface separately to obtain the input/output Schema for a Task registered name.

The local CLI checks the current environment directly, without HTTP. If the service uses another virtual environment, local CLI results may not represent the persistent service's environment.

## Build and inspect from source

The repository's a158 directory is an example source path:

```bash
axonx plugin inspect ./plugins/a158
axonx plugin build ./plugins/a158 --output ./dist/plugins
```

Source builds require pyproject, manifest, and valid contributions. The tool builds a wheel and checks its contents. Building does not run a research task or require Task submission.

Without `--output`, the CLI's default cache is `.axonx/plugins/artifacts/<content_sha256>` under the current directory. The plugin CLI chooses this cache path itself; it does not automatically follow another service's workspace_dir.

Existing wheels can be inspected/installed directly, but cannot be combined with `--output`:

```bash
axonx plugin inspect './dist/plugins/<actual wheel filename>.whl'
```

## Local installation

```bash
axonx plugin install ./plugins/a158
# Editable installation is optional for plugin development and only changes the current environment
axonx plugin install -e ./plugins/a158
```

editable only supports local source directories, not `--target` or `--output`. The environment can read source changes during development, but already assembled Jobs/Components in a persistent Application should still be reloaded through a restart.

The service's `plugins.sources` configuration can install sources at startup; see [Configuration reference](../reference/configuration.md) for path resolution. Installed valid plugins are discovered through entry points, rather than an explicit enablement list copied from another project.

## Deploy remotely

```bash
export AXONX_TARGET_TOKEN='<remote service token>'
axonx plugin list --target 'http://research.example:1024'
axonx plugin install ./plugins/a158 --target 'http://research.example:1024'
```

The CLI builds local source into a wheel, uploads it to remote `/files`, checks the returned sha256, then calls remote install_plugin and cleans up staging files at the end. The installation Job runs in the target service's Python environment.

`plugin build` only runs locally and does not support `--target`. Remote inspect queries installed plugins on the target; it does not send a local source directory to the target for inspection.

## Checksums and restart

| Field            | Explanation                                                             |
| ---------------- | ----------------------------------------------------------------------- |
| content_sha256   | Content/source fingerprint for build caching and content identification |
| sha256           | Specific wheel file checksum for transfer and installation verification |
| restart_required | The current application must restart to reassemble plugin contributions |

The two sha256 fields are not guaranteed to match: wheel compression and packaging change the specific file bytes. Pass the wheel sha256 from the upload receipt to the installation interface, not the source fingerprint.

Successful installation only means the environment change completed. Restart the execution service as indicated by restart_required, then query:

```bash
axonx list_installed_task_definitions --target 'http://research.example:1024'
axonx get_task_definition --task '<plugin Task registered name>' \
  --target 'http://research.example:1024'
```

## Uninstallation and troubleshooting

```bash
axonx plugin uninstall '<distribution or plugin name>'
axonx plugin uninstall '<distribution or plugin name>' \
  --target 'http://research.example:1024'
```

Uninstallation affects future code loading but does not automatically delete historical research artifacts. Existing metadata remains readable, though reruns may require restoring the original plugin version.

| Problem                                       | Check                                                                    |
| --------------------------------------------- | ------------------------------------------------------------------------ |
| Registered name conflict                      | Whether plugin contributions share names with built-ins or other plugins |
| Invalid manifest                              | Types, module:Class, Task docstrings, and class base classes             |
| Installation succeeded but UI has not updated | restart_required, target machine, and runtime environment                |
| Wheel checksum failed                         | Use the upload receipt sha256 and transfer the correct file again        |
| Missing model dependencies                    | requirements and device libraries in the target environment              |

[Plugin manifest](../reference/plugin-manifest.md) · [Remote machines](remote-machines.md) · [Existing development guide](../dev_guide.md)

Source: [Plugin CLI](../../../axonx/plugin_kit/cli.py), [Wheel building](../../../axonx/plugin_kit/wheel.py), [Installer](../../../axonx/plugin_kit/installer.py).
