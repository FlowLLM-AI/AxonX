# Server configuration reference

Service configuration describes an Application's workspace, components, Jobs, schedules, and HTTP service. CLI `start` uses ConfigResolver to resolve YAML/JSON first, then validates it with ApplicationConfig. Constructing an Application directly in Python does not automatically read default.yaml; explicitly call the resolver or supply complete configuration.

![Configuration resolution and overrides](../../figures/reference/config-resolution.svg)

## Minimal override configuration

```yaml
extends: default
workspace_dir: .axonx
log_dir: logs
service:
  host: 127.0.0.1
  port: 1024
  token: ${AXONX_SERVICE_TOKEN}
```

```bash
axonx start --config app.yaml
axonx start --config app.yaml --service.port 2024
```

extends is not a persistent ApplicationConfig field; the resolver removes it first. See [Python reference](python.md) for Python usage.

## ApplicationConfig

The table lists model defaults, which differ from the expanded built-in default.yaml. For example, model components/jobs are empty, while default.yaml configures task components, an Agent, and multiple Jobs.

| Field          | Type                                      | Model default | Meaning and constraints                                    |
| -------------- | ----------------------------------------- | ------------- | ---------------------------------------------------------- |
| app_name       | string                                    | AxonX         | Display name in logs and protocols                         |
| workspace_dir  | string                                    | .axonx        | Root directory for tasks, artifacts, and application state |
| log_dir        | string                                    | logs          | Service and task log directory                             |
| timezone       | string                                    | Asia/Shanghai | Default application/task timezone                          |
| language       | `en` / `zh`                               | en            | Built-in Agent guide language                              |
| enable_logo    | boolean                                   | true          | CLI start prints the startup logo                          |
| log_to_console | boolean                                   | true          | Console logging                                            |
| log_to_file    | boolean                                   | true          | File logging                                               |
| plugins        | PluginConfig                              | sources=[]    | Startup plugin sources                                     |
| targets        | TargetConfig[]                            | []            | Service targets to which the backend may forward           |
| environment    | dict[string,string]                       | {}            | Application environment injected into workers and Agents   |
| components     | dict[category,dict[name,ComponentConfig]] | {}            | Named component groups                                     |
| jobs           | dict[public_name,JobConfig]               | {}            | Job definitions                                            |
| schedules      | dict[name,ScheduleConfig]                 | {}            | Schedulers                                                 |
| service        | ComponentConfig/null                      | null          | Service component; CLI start requires service              |

The model prohibits unknown top-level fields. Normalized target addresses must not be duplicated. environment values must be strings, rather than numbers or nested objects.

## Configuration discovery and inheritance

`--config default` and `--config remote` locate built-in named configurations. Packages may contribute other names through the `axonx.configs` entry point; collisions between built-in and external names, or among external names, are rejected. File paths support .yaml/.yml/.json. Relative file paths are tried against the current working directory first, then the built-in configuration directory.

```yaml
extends:
  - default
  - ./research-base.yaml
service:
  port: 2024
```

Parent configurations merge from left to right in the list; the current file overrides parents, and explicit CLI/Python overrides apply last. Dictionaries merge recursively and lists are replaced in full; two steps or targets arrays are not concatenated. Relative extends files are sought first in the current configuration file's directory. Cyclic inheritance raises an error.

```yaml
# The parent's targets are replaced in full; other names in jobs are retained.
extends: default
targets:
  - address: http://node-b:1024
    token: ${NODE_B_TOKEN}
jobs:
  version:
    enable_stream: false
```

## Environment expansion and paths

`${VAR}` requires the variable to exist; `${VAR:-default}` uses the default text when the variable is absent. An existing but empty variable does not use default. Each file is recursively expanded before inheritance merging. Only strings whose content changes during environment substitution are then converted from true/false, null, numbers, or JSON to natural values; unchanged strings retain their original type.

```yaml
service:
  token: ${AXONX_SERVICE_TOKEN:-null}
  web_enabled: ${AXONX_SERVICE_WEB_ENABLED:-true}
  shutdown_timeout: ${AXONX_SERVICE_SHUTDOWN_TIMEOUT:-1}
```

CLI start first loads .env and merges it into environment. Ordinary clients and exec read the environment with override=false. Python's ConfigResolver does not itself load .env; callers must establish the environment themselves.

Relative plugins.sources paths resolve to absolute paths against the configuration file that declares them. Ordinary paths such as workspace_dir/log_dir do not receive this special conversion; at runtime, they are usually relative to the process working directory and support user-directory expansion. The configuration file's directory is not the base for all paths.

## ComponentConfig and named components

ComponentConfig requires a nonempty backend and allows extra fields, interpreted or validated by the corresponding implementation constructor.

```yaml
components:
  task_repository:
    default:
      backend: local
      recursive: true
      force_polling: true
      debounce: 3000
      step: 3000
      poll_delay_ms: 1000
  task_manager:
    default:
      backend: local
      task_repository: default
      terminate_grace_seconds: 5
      reaper_interval_seconds: 5
```

task_repository is the category, default is the instance name, and local is the implementation backend. TaskManager declares a dependency on the repository. Composition checks instance existence and type; dependencies start first and close last. See [Framework extensions](../development/framework-extensions.md).

## JobConfig

| Field         | Type               | Default                   | Meaning                                                     |
| ------------- | ------------------ | ------------------------- | ----------------------------------------------------------- |
| backend       | Nonempty string    | pipeline                  | Job implementation                                          |
| description   | string             | Empty string              | Public description                                          |
| parameters    | JSON Schema object | type=object,properties={} | Must describe an object; missing type is filled with object |
| enable_serve  | boolean            | true                      | Eligible for the HTTP/MCP public catalog                    |
| enable_stream | boolean            | true                      | Allow live HTTP streaming                                   |
| requires_auth | boolean            | true                      | Exclude this Job when no service token is configured        |
| steps         | ComponentConfig[]  | []                        | Execute asynchronous Steps sequentially                     |
| defaults      | object             | {}                        | Default Job context values                                  |

PipelineJob also supports event_buffer_size (default 64, a positive integer) as a backend-specific extra field. JSON Schema default in parameters is descriptive; do not assume the framework injects it uniformly. Actual defaults must be handled by defaults or a Step. System-injected values are isolated from public parameters.

## ScheduleConfig

| Field              | Type                 | Default  | Meaning                                   |
| ------------------ | -------------------- | -------- | ----------------------------------------- |
| backend            | Nonempty string      | cron     | Scheduler implementation                  |
| job                | Nonempty string      | Required | Job name to invoke                        |
| cron               | Nonempty string      | Required | Cron expression                           |
| arguments          | object               | {}       | Job arguments                             |
| timezone           | Nonempty string/null | null     | null uses the application timezone        |
| concurrency_policy | forbid/allow/replace | forbid   | Overlap policy for the same scheduled Job |

The default is schedules={}. Policies apply to execution of the scheduled Job; after submit returns, the background Task may still be running. See [Scheduling](../guides/scheduling.md) for an enabling example.

## PluginConfig and TargetConfig

plugins accepts only sources, an array of nonempty strings defaulting to []. Plugins already installed in the environment are also discovered; sources is not an exclusive enablement allowlist. Startup sources may trigger installation; confirm the source code and dependencies being used first.

TargetConfig strictly prohibits extra fields: address is required and nonempty; token defaults to null or is a nonempty string. Addresses accept host:port or HTTP(S) URLs with explicit ports. User/password credentials, subpaths, query, and fragment are prohibited; normalization removes trailing slashes. See [Client connections](client-configuration.md) for complete usage.

## HTTP service

| Field            | Default        | Explanation                                                            |
| ---------------- | -------------- | ---------------------------------------------------------------------- |
| backend          | Required: http | HTTP service implementation                                            |
| host             | 0.0.0.0        | Bind address                                                           |
| port             | 1024           | Listening port                                                         |
| shutdown_timeout | 1              | Uvicorn graceful-shutdown seconds; nonnegative                         |
| web_enabled      | true           | Whether to mount the Studio static build                               |
| token            | null           | Nonempty Bearer token; null filters the catalog according to Job rules |

The service has no TLS configuration by default. A missing Studio build is logged as unavailable; the API can still run. Configuration updates do not recompose the application live; restart and verify the catalog again.

## Topic-specific configuration and validation

- [Claude Agent](../agent/configuration.md): models, permissions, tools, and session state.
- [Task synchronization](../guides/task-sync.md): sync components and schedules disabled by default.
- [HTTP proxy](../guides/http-proxy.md): named fixed upstreams.
- [Service deployment](../guides/deployment.md): process supervision and static resources.

When startup raises ValidationError, first check top-level spelling, strict TargetConfig token types, environment strings, and registered backend names. Missing or conflicting dependencies are composition errors and cannot be resolved by skipping Schema validation.

Implementation references: `axonx/config/models.py`, `resolver.py`, `default.yaml`, `core/composition.py`, `components/service/http/service.py`.
