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
