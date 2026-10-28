# Contributing to AxonX

This area covers framework and Studio development. Implement research algorithms in plugins using the [development and operations guide](../dev_guide.md) under Research. Start Agent-driven plugin development with [Skill and research prompt](../agent/research-prompt.md).

## Choose a contribution scope

| Goal                                           | Guide                                           | Related contracts                                                                                  |
| ---------------------------------------------- | ----------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Prepare source and checks                      | [Contribution guide](../../../CONTRIBUTING.md)  | Repository contribution requirements                                                               |
| Extend Components, Jobs, or asynchronous Steps | [Framework extensions](framework-extensions.md) | [Architecture](../concepts/architecture.md), [server configuration](../reference/configuration.md) |
| Develop Studio features and artifact views     | [Studio development](studio.md)                 | [Research artifact contracts](../reference/research-artifacts.md)                                  |
| Integrate a service client                     | [Python reference](../reference/python.md)      | [HTTP API](../api/overview.md), [events](../api/events.md)                                         |

## Preserve responsibility and resource boundaries

Reuse framework extension points and preserve public CLI, API, configuration, Task identity, lifecycle, and persisted record contracts. Make ownership and cleanup explicit for asynchronous resources, streams, and subprocesses. Keep research algorithms, features, and portfolio policies in plugins.

Use temporary workspaces for focused checks, then run affected tests and formatting as required by the [contribution guide](../../../CONTRIBUTING.md). Report implementation verification separately from research improvement evidence.

## Maintain documentation and the site

Update English and Chinese together. Guides own procedures, [Reference](../reference/overview.md) owns fields, plugin READMEs own algorithms, and case studies own specific experiments. The [site maintenance guide](../../../github-pages/README.md) covers navigation, generation, and build verification.

## Documentation ownership and validation

The source of truth for public Job arguments is `axonx/app/config/default.yaml`; native command syntax belongs to `axonx/cli/parser.py` and execution behavior to `commands.py`/`remote.py`. Task models and authoring interfaces live under `axonx/task`. Update references, examples, diagrams and both languages together when these contracts change.

The built-in Agent resources are symlinks to docs/en/dev_guide.md and docs/zh/dev_guide.md. Keep these canonical guides runnable and synchronize the distributable skills/axonx/SKILL.md body with the English guide. Persistent services reload guides at startup.

From the repository root, run `python -m pytest tests/unit/test_documentation_contracts.py` in the backend development environment, then `npm --prefix github-pages test` and `npm --prefix github-pages run build` with both frontend dependency sets installed. Contract checks validate all configured Job request examples, documented CLI inputs/imports and runnable Task authoring/composition. The site build additionally validates navigation, translations, anchors, assets and exports. Historical research tables and benchmark figures retain their recorded values and provenance.
