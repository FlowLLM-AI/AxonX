# Plugin packages and contribution contracts

A plugin is a Python distribution with an `axonx.plugins` entry point and a packaged plugin.yaml. Its manifest declares Tasks, managed component backends, and Jobs; installation and runtime composition are separate phases. Inspect package metadata and declarations first, then start the application and verify registered definitions and public Jobs.

![Plugin discovery and contributions](../../figures/reference/plugin.svg)

## Three kinds of names

| Name                   | Example       | Where it is used                                         |
| ---------------------- | ------------- | -------------------------------------------------------- |
| distribution           | axonx-example | pip metadata, installation, and uninstallation           |
| plugin entry point     | example       | Plugin discovery and the package containing the manifest |
| Task registration name | example_task  | submit.task, get_task_definition.task                    |

These names need not match. A Task ID is separately composed of task type, registration name, and instance name; a distribution name cannot substitute for a registration name when executing a task.

## Minimal package layout

```text
example-project/
  pyproject.toml
  axonx_example/
    __init__.py
    plugin.yaml
    tasks.py
```

pyproject.toml:

```toml
[build-system]
requires = ["setuptools>=84.0.0"]
build-backend = "setuptools.build_meta"

[project]
name = "axonx-example"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["axonx>=0.1.0"]

[project.entry-points."axonx.plugins"]
example = "axonx_example"

[tool.setuptools.packages.find]
where = ["."]
include = ["axonx_example*"]

[tool.setuptools.package-data]
axonx_example = ["plugin.yaml"]
```

The entry point targets a Python package; plugin.yaml must be included in the wheel. A manifest present only in source without package-data inclusion causes discovery to fail after installation.

## Manifest fields

```yaml
tasks:
  example_task: axonx_example.tasks:ExampleTask
components: {}
jobs: {}
```

| Field      | Type                                       | Default | Contract                                                       |
| ---------- | ------------------------------------------ | ------- | -------------------------------------------------------------- |
| tasks      | dict[nonempty_name,nonempty_symbol_target] | {}      | Symbols must be BaseTask subclasses                            |
| components | dict[category,dict[backend,symbol_target]] | {}      | Symbols must be BaseComponent subclasses matching the category |
| jobs       | dict[nonempty_name,JobConfig]              | {}      | JobConfig uses the same model as service configuration         |

Extra top-level fields are prohibited, and the root must be a YAML mapping. Names and string targets are stripped of surrounding whitespace and must be nonempty. A `module:Class` target imports the module, then resolves attributes one level at a time. Invalid target format, missing attributes, or a symbol that does not extend the required base class causes failure. Tasks may import helpers from additional packages or standalone modules shipped in the same wheel; service installation refreshes those modules as well as the entry-point package.

Tasks must declare a fixed TaskType, input_cls, and output_cls. A detailed class docstring is recommended; description is extracted from it when definitions are queried, or returned as an empty string if it is missing or whitespace-only. See the [Existing development guide](../dev_guide.md) for a minimal Task development workflow.

All registered Tasks must follow the public authoring contract in
[`BaseTask`](../../../axonx/task/core/task.py). The research base classes in
[`axonx.task.contracts`](../../../axonx/task/contracts/) are optional standard contracts; adopting them requires
preserving their parameter fields and validation rules. See [Required authoring contracts](../dev_guide.md#required-authoring-contracts)
for implementation requirements and the distinction between core and research contracts.

## Job and component contributions

The following Job uses the built-in version_step and requires no new Step:

```yaml
tasks: {}
components: {}
jobs:
  example_version:
    description: Return version through the plugin job.
    parameters:
      type: object
      properties: {}
      additionalProperties: false
    steps:
      - backend: version_step
```

See [Configuration reference](configuration.md#jobconfig) for all JobConfig fields. A plugin Job sharing a name with application configuration raises an error; configuration does not automatically override the plugin.

Component contributions declare only backend implementations; instances are still configured through ApplicationConfig.components:

```yaml
# Declaration excerpt from plugin.yaml
components:
  proxy:
    example_proxy: axonx_example.proxy:ExampleProxy
```

```yaml
# Instance excerpt from app.yaml; ExampleProxy must extend BaseProxyComponent
components:
  proxy:
    reports:
      backend: example_proxy
```

The current loader constrains components to BaseComponent subclasses. BaseStep extends ComponentBase rather than BaseComponent, so custom BaseStep implementations cannot be placed directly in manifest components.step. Such local extension examples use Application(providers=...); see [Framework extensions](../development/framework-extensions.md). Category names alone do not imply that every Provider can be loaded from a manifest.

## Discovery, installation, and composition

With empty sources, startup inspects plugins already installed in the current environment. With nonempty sources, it first prepares installation/building of those sources, then returns the environment's plugin catalog. sources is neither a simple list of enabled names nor an allowlist restricting loading to those plugins.

```yaml
extends: default
plugins:
  sources:
    - ./plugins/example
```

This path resolves against the configuration file that declares it. For remote deployment, use CLI build/install or upload a wheel; a remote service cannot interpret a client's source-directory path.

Application uses a local registry and merges discovered contributions according to ownership. Two plugins with the same Task registration name, Job name, or category/backend are rejected; Task names colliding with built-ins are also rejected. Providers cannot be freely added after the registry is frozen.

## Wheels and content fingerprints

| Field            | Meaning                                 | Purpose                                       |
| ---------------- | --------------------------------------- | --------------------------------------------- |
| sha256           | SHA-256 of wheel file bytes             | Upload and installation artifact verification |
| content_sha256   | Plugin content fingerprint              | Build caching and content identity            |
| requirements     | Wheel dependency metadata               | Installation environment requirements         |
| restart_required | Installation/uninstallation result hint | Recompose service contributions               |

Identical source content and caching do not guarantee identical wheel bytes; do not substitute content_sha256 for the sha256 returned by upload. Remote install must receive the path and sha256 returned by POST /files. Editable installation applies only to local source environments and cannot be deployed remotely.

```bash
axonx plugin inspect ./plugins/example
axonx plugin build ./plugins/example --output ./dist
axonx plugin install ./plugins/example
axonx plugin list
```

These commands inspect, build, or install and must be used with an actual plugin directory. When an installation result requires a restart, query get_task_definition and /jobs after restarting to verify contributions. Task-only wheel installation through the service refreshes subsequent Task queries and submissions without restarting; already assembled Components/Jobs still require restart. See [Plugin management](../plugins/management.md#checksums-and-restart).

## Named configuration contributions

The same package can also publish an axonx.configs entry point:

```toml
[project.entry-points."axonx.configs"]
example = "axonx_example.config:example"

[tool.setuptools.package-data]
axonx_example = ["plugin.yaml", "config/*.yaml"]
```

If attr is an existing object, the resolver loads it and, if callable, calls it to obtain a YAML/JSON path. Otherwise, it treats the target package as a directory and locates the corresponding configuration file by attr/name. The result must identify an actual configuration file. Ambiguous identical configuration names are rejected rather than silently selecting one.

The repository's a158 uses the separate distribution axonx-alpha158, plugin entry point alpha158, and package axonx_alpha158, providing a real package-layout reference.

## Related documentation

- [Plugin management](../plugins/management.md)
- [Plugin API](../api/plugins-sync.md)
- [CLI reference](cli.md)

Implementation references: `plugin_kit/manifest.py`, `loading.py`, `contributions.py`, `runtime.py`, `wheel.py`, `config/resolver.py`.
