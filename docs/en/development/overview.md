# Develop and extend AxonX

Keep research algorithms in plugins and reuse the framework's extension points for execution, records, and interfaces. Choose the layer you need to extend before changing code.

## Choose an extension path

| Goal                                           | Start here                                          | Contract to consult                                                             |
| ---------------------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------------------- |
| Prepare a source checkout and run checks       | [Contributing](../../../CONTRIBUTING.md)            | Repository contribution rules                                                   |
| Implement a research Task                      | [Development and operations guide](../dev_guide.md) | [Task inputs, outputs, identity, and lifecycle](../reference/task-contracts.md) |
| Package and register a plugin                  | [Plugin management](../plugins/management.md)       | [Plugin manifest](../reference/plugin-manifest.md)                              |
| Extend components, Jobs, or asynchronous steps | [Framework extensions](framework-extensions.md)     | [Architecture](../concepts/architecture.md)                                     |
| Build Studio features and artifact views       | [Studio development](studio.md)                     | [Research artifacts](../reference/research-artifacts.md)                        |
| Integrate a service client                     | [Python reference](../reference/python.md)          | [HTTP API](../api/overview.md) and [events](../api/events.md)                   |

The development and operations guide is also bundled for optional built-in Agent loading. Its canonical `dev_guide.md` path remains available to external Skills and source links; focused pages own the deeper explanations and field references.

## Validate the research change

Discover the registered Task's schema, exercise a minimal execution in a temporary workspace, and inspect its output metadata and declared artifacts. Changes to feature timing, fields, or upstream requirements need compatibility checks before reusing earlier records.

Use [experiment design](../research/experiments.md) for algorithm comparisons and [external agents](../agent/external.md) for agent-driven development. The [Qlib Factor plugin](../../../plugins/qlib_factor/README.md) demonstrates a separate implementation with feature-group switches and recorded comparisons.

## Maintain the documentation

Update English and Chinese pages together. Keep algorithm details with plugins, general workflows in guides, and field definitions in references. The [site maintenance guide](../../../github-pages/README.md) explains navigation ownership, generation, and build checks.
