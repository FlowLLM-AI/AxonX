# Scheduling

Schedules launch local synchronous Task commands. The application determines future trigger times; the daemon owns launched processes.

![Cron process ownership](../../figures/guides/scheduling.svg)

## Minimal configuration

```yaml
extends: default
timezone: Asia/Shanghai
cron:
  - expression: "0 16 * * 1-5"
    command: "axonx exec --task download_tushare_task --days-back 7"
```

Start with `axonx app --config scheduled.yaml`. Set `cron: []` to disable inherited schedules. The whole list replaces its parent list. Restart to reload edits.

## Cron and time zones

Expressions have exactly five numeric fields: minute, hour, day, month, weekday. Numeric ranges, lists, steps and wildcards are supported; named weekdays and a seconds field are rejected. The application timezone controls trigger calculation. Each due entry triggers once, then advances from the current time; missed occurrences are not replayed.

## Command arguments

Commands must start with `axonx exec` and include a nonempty `--task NAME`. Parsing uses `shlex`, without a shell. Pipes, redirection, environment assignments and client options such as `--target` are not supported. Configure execution defaults and environment at application level, or use explicit Task execution fields.

## Concurrency and identity

There is no named schedule record, scheduler concurrency policy or automatic skip/replace queue. A trigger requests a new daemon-owned command. Different generated Task names keep separate records; a fixed `--task-name` reuses a directory and requires caller coordination. A running same-name record causes startup rejection. Build business overlap policy explicitly in a Task or host integration.

## Checks and shutdown

Check daemon/service logs and `logs/cron/entry-N.log`, then the Task metadata and artifacts. A launched process alone does not prove success. Stopping the application halts future triggers. Daemon-owned scheduled executions survive application service restart; manual service-owned CLI commands are stopped during service shutdown. Replacing source/dependencies while scheduled commands remain active requires coordination because processes are not version-isolated.

## Embedded applications

`Application(cron=..., launch_scheduled=callback)` requires a host-provided launcher. The callback receives the entry index and `CronConfig`; the host owns process lifetime. CLI startup injects the daemon launcher. See [Framework extensions](../development/framework-extensions.md).

Sources: [CronConfig](../../../axonx/app/config/models.py), [trigger loop](../../../axonx/app/components/cron/scheduler.py), [daemon launcher](../../../axonx/daemon/launcher.py).
