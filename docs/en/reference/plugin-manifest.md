# Plugin Manifest

![Task registration discovery](../../figures/reference/plugin.svg)

## Names and package layout

A distribution publishes an `axonx.plugins` entry point whose value is a Python package containing `plugin.yaml`. Registration names are keys, class targets use `module:Class`.

```text
example/
  pyproject.toml
  example_plugin/
    __init__.py
    plugin.yaml
    task.py
```

```toml
[project]
name = "axonx-example"
version = "0.1.0"
dependencies = ["axonx>=0.3.0"]

[project.entry-points."axonx.plugins"]
example = "example_plugin"

[tool.setuptools.package-data]
example_plugin = ["plugin.yaml"]
```

```yaml
tasks:
  example_add: example_plugin.task:AddTask
```

Use the runnable Task class from the [development guide](../dev_guide.md). Task names must be unique across installed distributions and built-ins.

## Manifest fields

The only accepted field is `tasks`, a mapping of nonempty registration names to nonempty class targets. Unknown manifest fields are rejected. Discovery reads manifests without loading Task code; TaskCatalog imports and validates subclasses lazily. A Task class docstring becomes its definition description. Inputs/outputs come from its Pydantic model schemas.

## Framework extensions

Components and Jobs belong to application configuration and explicit `Application(providers=...)` composition. A Task manifest does not register them. An installed package may independently provide `axonx.configs` entry points for configuration files; this is not a field in the Task manifest.

## Discovery, installation and composition

Install the distribution into the actual execution interpreter. The launcher snapshots Task registrations at service startup; each new `exec` builds a fresh catalog. Classes are cached within each catalog. Installation and uninstallation do not refresh an existing catalog or serialize environment changes. Restart persistent services after registration, schema or loaded dependency changes.

Source paths in native remote commands belong to the target machine. Local-to-remote deployment explicitly builds, uploads to `/upload`, installs `location`, cleans up `path`, and verifies after restart. See [Plugin management](../plugins/management.md).

## Wheels and content fingerprints

| Field            | Meaning                                   |
| ---------------- | ----------------------------------------- |
| `sha256`         | Exact wheel bytes                         |
| `content_sha256` | Normalized plugin content                 |
| `requirements`   | Declared dependency metadata              |
| `tasks`          | Registration → class target               |
| `wheel`          | Artifact location in build/inspect output |

The installer installs declared dependencies except AxonX itself, installs the plugin with force-reinstall/no-deps, and checks installed provenance/content against the target wheel. It does not accept an expected hash from the caller. Compare returned `sha256` with the local wheel hash when validating transport. Editable source needs a fresh interpreter for import hooks and may require a persistent service restart.

## Named configuration contributions

```toml
[project.entry-points."axonx.configs"]
example = "example_plugin.config:service"
```

This locates `service.yaml`, `.yml` or `.json` in the target package directory. Include configuration files as package data. Names must not collide with built-ins or other installed providers. Configuration inheritance follows [Configuration reference](configuration.md).

Sources: [manifest](../../../axonx/plugin/manifest.py), [discovery](../../../axonx/plugin/discovery.py), [wheel tools](../../../axonx/plugin/wheel.py).
