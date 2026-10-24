# 定时执行 Task

启动服务时指定命名 crontab 或明确的 `.cron` 文件路径：

```bash
axonx start --config default --cron research
axonx start --config default --cron ./research.cron
```

`research` 对应 `axonx/cron/research.cron`，内含注释掉的模板。复制为自己的文件并启用所需条目。省略 `--cron` 且应用配置未设置 `cron` 时，不启用调度。

## Crontab 格式

```text
# 分 时 日 月 星期 命令
0 16 * * 1-5 axonx exec --task download_tushare_task --days-back 7
*/10 * * * * axonx exec --task demo --task-name cron-demo --x 1 --y 2
```

每行由五个数字 cron 字段、`axonx exec --task NAME` 和成对的 Task 参数组成。支持数字、`*`、列表、范围和步长。忽略空行及整行 `#` 注释。包含空格或 Task ID 的值可写成 `'etl#data#daily'`；命令中的 `#` 会保留。不支持行尾注释、环境赋值、用户列、宏、秒字段及英文月份／星期名。

命令由 daemon 在本机使用同一 Python 解释器、启动工作目录、配置的环境变量、绝对 workspace／日志路径和应用时区执行。插件需要安装在同一环境。执行不经过 shell，拒绝管道、重定向、命令串联及 `--target` 等客户端参数。参数里的 shell 变量、命令替换和 `~` 保持原文，不会展开。

启动时一次性读取并校验整个文件，修改后重启服务生效。允许执行重叠；启动失败只记录日志，不重试，停机期间错过的时间点不补跑。关闭服务只停止后续触发，已启动的 exec 进程继续运行。同名 Task 不会自动串行化，应合理设置时间与 Task 名称，避免同时写入同一 Task 目录。

## 定位与配置

```yaml
extends: default
cron: ./research.cron
timezone: Asia/Shanghai
```

`--cron` 覆盖 YAML 的 `cron`。config 与 cron 复用名称／路径定位，各自独立解析。内置名称来自 `axonx/cron/`；安装包可通过 `axonx.crons` entry point 注册名称，冲突时报错。相对 `.cron` 路径先在启动目录查找，再在 `axonx/cron/` 下查找。cron 文件不支持 YAML 继承、合并或直接传入文本内容。

插件注册示例：

```toml
[project.entry-points."axonx.crons"]
research_team = "my_plugin.crons:research"
```

将 `research.cron` 作为包数据放入 `my_plugin/crons/`。entry point 也可指向返回 `.cron` 路径的属性或函数。

## 观察执行

实际状态、日志和产物在普通 Task 列表中按 Task/Run ID 查看。cron 不提供查询 Job 或 Studio 页面。

cron worker 只发送触发请求，daemon 创建并回收 exec 子进程。各行命令的 stdout/stderr 追加到 `<log_dir>/cron/line-N.log`。Task metadata 与普通 Run 日志由 exec 写入。cron 不额外持久化执行历史，也不管理 Task 进程。旧 `schedules` 映射、scheduler 组件后端及 Job 调度全部删除，不保留兼容。
