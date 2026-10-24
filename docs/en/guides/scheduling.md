# Scheduled Task execution

Start the service with a named crontab or an explicit `.cron` file:

```bash
axonx start --config default --cron research
axonx start --config default --cron ./research.cron
```

`research` resolves to `axonx/cron/research.cron`, a commented template. Copy it to your own file and enable the entries you need. Omitting `--cron` leaves scheduling disabled unless `cron` is set in the application configuration.

## Crontab format

```text
# minute hour day-of-month month day-of-week command
0 16 * * 1-5 axonx exec --task download_tushare_task --days-back 7
*/10 * * * * axonx exec --task demo --task-name cron-demo --x 1 --y 2
```

Each entry has five numeric cron fields followed by `axonx exec --task NAME` and paired Task options. Numeric values, `*`, lists, ranges and steps are supported. Blank lines and whole-line `#` comments are ignored. Quote values containing spaces or Task IDs such as `'etl#data#daily'`; `#` inside a command is preserved. Inline comments, environment assignments, user columns, macros, seconds fields and named months/weekdays are unsupported.

Commands run locally under the daemon with its Python interpreter, startup working directory, configured environment, absolute workspace/log paths and application timezone. Plugins must be installed in that environment. There is no shell: pipes, redirects, chained commands and client options such as `--target` are rejected. Shell variables, command substitutions and `~` in argument values remain literal; cron does not expand them.

The complete file is validated and read once during startup. Edit it and restart the service to apply changes. Scheduled commands may overlap. Failed launches are logged without retry; downtime does not replay missed slots. Service shutdown stops future triggers while already started exec processes continue. Same-name Task executions are not serialized; use schedules and Task names that avoid concurrent writes to the same Task directory.

## Lookup and configuration

```yaml
extends: default
cron: ./research.cron
timezone: Asia/Shanghai
```

`--cron` overrides `cron` in YAML. Config and cron share name/path discovery, while their parsing stays separate. Built-in names come from `axonx/cron/`; installed packages can contribute names through `axonx.crons` entry points. Name collisions are rejected. Relative `.cron` paths are tried against the startup directory, then `axonx/cron/`. Cron files do not support YAML inheritance, merging or inline content.

Package contribution example:

```toml
[project.entry-points."axonx.crons"]
research_team = "my_plugin.crons:research"
```

Include `research.cron` as package data in `my_plugin/crons/`. Alternatively, the entry point may expose an attribute or callable returning a `.cron` path.

## Observation

Inspect execution state, logs and outputs in the ordinary Task list using Task/Run IDs. Cron has no query Job or Studio page.

The cron worker only sends trigger requests; the daemon creates and reaps exec children. Each cron line appends command stdout/stderr to `<log_dir>/cron/line-N.log`. Task metadata and normal Run logs are written by exec. Cron does not persist a second execution history or manage Task processes. The old `schedules` mapping, scheduler component backends and Job scheduling are removed without compatibility.
