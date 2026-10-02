---
name: axonx-harness-skill
description: 在 AxonX 仓库中开发量化研究插件，并通过 CLI 安装、提交、跟踪 ETL、Analysis、Train、Predict、Backtest Task 和检查产物时使用。
---

# AxonX Harness

## 背景

AxonX 是面向金融量化研究的 Harness 框架，将数据获取与 ETL、因子分析、模型训练、预测和回测组织为遵循统一输入输出契约的 Task。
研究实现由插件注册，Task 通过 Task ID 关联上下游，CLI 和 HTTP 服务支持在本地或远程机器提交执行，并查询机器资源、运行状态与日志。
框架在工作区记录任务配置、依赖、结果元数据和产物，向 Agent 提供任务、依赖图和文件查询工具，便于验证研究结果、排查失败并复用上游数据。

- 鉴权：服务启用鉴权时，提前在环境变量或 `.env` 中配置本地 `AXONX_SERVICE_TOKEN` 或远程 `AXONX_TARGET_TOKEN`。
- 本地操作：使用表格中的“命令”，不传 `--target`。通过本机 AxonX HTTP 服务直接提交、查询 Task 和查询机器资源。
- 发现远程机器：使用 `axonx list_machines` 查询本地服务 `targets` 中所有已配置机器的地址（`address`，如
  `http://192.168.1.10:1024`）及对应的健康状态（`healthy`），再用 `axonx machine_status --target <host:port>` 查看候选机器的
  CPU、内存和 GPU。
- 远程操作：已知目标地址时，在支持远程的命令末尾追加“远程参数”列中的 `--target <host:port>`。

表格中的 `192.168.1.10:1024` 是示例目标地址，执行前替换。`—` 表示不支持远程。

## 插件开发

插件可注册多个 Task；a158 示例在 `plugins/a158/axonx_alpha158/plugin.yaml` 中注册了五类 Task。本文的 a158
路径、类名、注册名和依赖链仅用于示例，开发其他研究插件时应替换为实际定义。插件安装与 Task 提交是独立操作。

### Task 类型

| 类型     | 概念与用途                                         |
|----------|----------------------------------------------------|
| ETL      | 清洗、对齐原始数据，生成供后续研究使用的数据集。   |
| Analysis | 分析 ETL 数据集中的因子，诊断因子质量与表现。      |
| Train    | 使用 ETL 数据集训练模型，产出模型及训练结果。      |
| Predict  | 使用 Train 产出的模型及其关联的 ETL 数据生成预测。 |
| Backtest | 使用 Predict 结果进行回测，评估策略表现。          |

Task 通过 Task ID 关联上下游。a158 示例的主要依赖链为 ETL → Train → Predict → Backtest，Analysis 使用 ETL 数据开展因子分析。

### 开发步骤

#### 1. 修改代码与注册

以 ETL 为例，最小结构包含输入参数、输出参数、Task 实现和注册。下面是结构示例，`transform` 中的 `...` 需替换为实际 ETL
逻辑，读取输入并将结果写入 `self.state["output"]`。

`plugins/a158/axonx_alpha158/etl.py`：

```python
from pathlib import Path

from axonx.task.contracts import BaseETLInputParams, BaseETLOutputParams, BaseETLTask


class Alpha158InputParams(BaseETLInputParams):
    input_dir: Path = Path("tushare")


class Alpha158OutputParams(BaseETLOutputParams):
    pass  # 直接使用 ETL 基类的输出字段


class Alpha158Task(BaseETLTask):
    """清洗并对齐原始行情，生成供训练和因子分析使用的 ETL 数据集。
    """

    input_cls = Alpha158InputParams
    output_cls = Alpha158OutputParams
    input_params: Alpha158InputParams

    def build_task_steps(self):
        yield self.transform

    def transform(self):
        # 从 self.resolve_workspace_path(self.input_params.input_dir) 读取数据，
        # 将产物保存到 self.task_dir，并填充 self.state["output"]。
        ...

    def build_output_params(self):
        return self.output_cls(**self.state["output"])
```

Task 类必须定义非空的类 docstring，用于 Task 定义的 `description`；缺少时，Task 解析和定义查询会抛出
`TypeError: Task ... must define a detailed class docstring`。应说明任务用途、输入及产物，不能只给方法添加 docstring。

`BaseETLOutputParams` 已定义必填字段 `output_file`、`rows`、`date_range`，因此 `self.state["output"]` 至少包含这三个字段；需要额外结果时，再在
`Alpha158OutputParams` 中添加字段。

`plugins/a158/axonx_alpha158/plugin.yaml` 注册 CLI 使用的 Task 名称：

```yaml
tasks:
  a158_etl: axonx_alpha158.etl:Alpha158Task
```

`a158_etl` 是提交时的 `--task` 值；冒号前是 Python 模块，冒号后是 Task 类名。

新建插件时，包目录需包含 `__init__.py`，并在 `pyproject.toml` 中声明插件入口和随包分发的注册文件；已有 a158 插件已配置这些内容：

```toml
[project.entry-points."axonx.plugins"]
alpha158 = "axonx_alpha158"

[tool.setuptools.package-data]
axonx_alpha158 = ["plugin.yaml"]
```

#### 2. 安装插件

从源码构建 wheel 并安装到当前 Python 环境：

```bash
axonx plugin install plugins/a158
```

在远程机器执行 Task 时，追加 `--target 192.168.1.10:1024`，CLI 会上传 wheel 并在目标服务安装。

#### 3. 确认插件与 Task 注册

- 确认安装：使用 `axonx plugin list` 确认目标插件已安装且 `error` 为空；返回的 `tasks` 映射键可作为 `--task` 注册名。
- 查看定义：使用 `axonx get_task_definition --task a158_etl` 查看所选 Task 的描述、类型及输入输出 schema。
- 统一目标：远程查询和提交均追加同一个 `--target 192.168.1.10:1024`；本机服务使用不同 Python 环境时，也应显式指定服务地址。

#### 4. 查看执行资源

- 使用 `axonx machine_status` 查询执行机器的 CPU、内存和 GPU；远程执行时追加 `--target 192.168.1.10:1024`。
- 确认机器满足研究任务的资源需求后，再向该服务提交 Task。

#### 5. 提交 Task

只运行本次改动需要的 Task，复用未受影响的成功上游产物。控制变量：仅改变待验证因素，其余数据、区间和参数与基线保持一致。

- 增加因子：ETL → Train → Predict → Backtest。
- 更新模型结构：Train → Predict → Backtest，复用已有 ETL。
- 更新仓位管理策略：只跑 Backtest，复用已有 Predict。

Analysis 仅在需要因子诊断时运行。以下命令按需选用。

| 命令名称 | 具体描述                                                       | 命令                                                                   | 远程参数                     |
|----------|----------------------------------------------------------------|------------------------------------------------------------------------|------------------------------|
| `submit` | 提交 ETL，清洗并生成数据集；示例指定数据开始日期。             | `axonx submit --task a158_etl --start-date 20150101`                   | `--target 192.168.1.10:1024` |
| `submit` | 提交 Analysis，分析指定 ETL 产物中的因子。                     | `axonx submit --task a158_factor --source-tasks '<etl_task_id>'`       | `--target 192.168.1.10:1024` |
| `submit` | 提交 Train，使用指定 ETL 数据集训练模型。                      | `axonx submit --task a158_train --source-tasks '<etl_task_id>'`        | `--target 192.168.1.10:1024` |
| `submit` | 提交 Predict，使用指定 Train 模型及其关联的 ETL 数据生成预测。 | `axonx submit --task a158_predict --source-tasks '<train_task_id>'`    | `--target 192.168.1.10:1024` |
| `submit` | 提交 Backtest，评估指定 Predict 的预测结果。                   | `axonx submit --task a158_backtest --source-tasks '<predict_task_id>'` | `--target 192.168.1.10:1024` |

- Task 注册名：`--task a158_etl` 对应 `plugin.yaml` 中 `tasks` 的键，指向 `axonx_alpha158.etl:Alpha158Task`；Task 注册名取自
  `axonx plugin list` 返回的 `tasks` 键， 用 `axonx get_task_definition --task a158_etl` 查看该 Task 的完整定义。
- 输入参数：由 Task 的 `input_cls` 定义类型和默认值，CLI 将连字符转为下划线，例如 `--start-date` 对应
  `Alpha158InputParams.start_date`，通过 `self.input_params.start_date` 读取；`--input-dir` 对应 `input_dir`，未声明的字段会被拒绝。
- Task命名：默认省略 `--task-name`，名称自动生成为 `YYYYMMDDHH` 加 4 位随机字母或数字，Task ID 如
  `etl#a158_etl#<生成名称>`。 仅在用户指定名称时传入； **复用显式名称会在前次完成后替换产物**。
- 返回值：完整检查响应的 `success` 和 `answer`。提交成功仅表示已接受执行，`answer` 包含 `task_id`、`run_id`、`task`， 不包含
  `state`；记录实际返回的两个 ID，用于等待本次运行。下游 `source-tasks` 使用成功上游的 `task_id`，不猜测 ID。
- 上下游关联：将成功上游返回的 Task ID 填入 `--source-tasks`；多个 ID 用英文逗号连接，如 `'<id1>,<id2>'`，留空表示无上游。
  下游通过上游 `metadata.json` 定位产物。
- 执行目标：本地省略 `--target`，远程追加表中的参数并替换为真实地址。

#### 6. 跟踪运行与检查产物

- 使用提交响应中的实际 Task ID 和 Run ID，在同一服务上等待运行、查询状态、读取日志和检查产物。
- 完整检查 `status`、`wait_task` 或 `stream_task` 的 `answer`：核对 `task_id`、`run_id` 和 `state`，并查看
  `result`、`error`、`exit_code`、`log_path` 及步骤进度等字段。`status` 的 `success` 表示查询成功，不能据此判断 Task 成功。
- `state` 为 `queued` 或 `running` 时继续等待；仅在 `succeeded` 时提交下游。`failed` 或 `cancelled` 时先检查错误和日志。
- `wait_task` 必须传入提交返回的 `task_id`、`run_id`，等待指定运行结束；同一 Task ID 被重新提交后，Run ID 会变化， 不匹配时会报错。可用
  `--poll-interval 1` 设置轮询间隔（秒，必须大于 0，默认 1）。 长任务用 `--client-timeout 86400` 增加客户端请求超时；它不设置
  Task 执行时限。`wait_task` 仅在最终状态为 `succeeded` 时返回 `success: true`。

| 命令名称        | 具体描述                                                | 命令                                                                                       | 远程参数                     |
|-----------------|---------------------------------------------------------|--------------------------------------------------------------------------------------------|------------------------------|
| `wait_task`     | 等待提交返回的指定运行结束，检查最终 `answer.state`。   | `axonx wait_task --task-id '<etl_task_id>' --run-id '<etl_run_id>' --client-timeout 86400` | `--target 192.168.1.10:1024` |
| `status`        | 查询已提交 ETL Task 的状态，确认是否成功。              | `axonx status --task-id '<etl_task_id>'`                                                   | `--target 192.168.1.10:1024` |
| `read_task_log` | 读取该 ETL Task 的最近日志，检查输出或排查失败原因。    | `axonx read_task_log --task-id '<etl_task_id>'`                                            | `--target 192.168.1.10:1024` |
| `preview_file`  | 检查成功 ETL 的元数据，取得数据集产物路径，供下游使用。 | `axonx preview_file --path 'etl/<etl_task_id>/metadata.json'`                              | `--target 192.168.1.10:1024` |

其他 Task 使用其实际 Task ID 和对应类型的工作区路径。实时跟踪、依赖图查询和数据预览等命令见下方 CLI API。

## CLI API

- 示例值：IP、Task ID 和上传路径占位符须替换为配置或服务返回的真实值。
- 参数格式：普通 Job 参数放在 Job 名之后；JSON 数组须作为一个 shell 参数传入。
- 执行超时：`shell` 的 `--timeout` 是 Job 执行超时；`--client-timeout` 是客户端请求超时，长时间等待 Task 时使用后者。
- 执行条件： **破坏性 Job 与 `shell` 仅在当前任务确有需要且目标已确认时执行**。

### 启动与本地执行

| 命令名称  | 具体描述                                                                                | 命令                                               | 远程参数                     |
|-----------|-----------------------------------------------------------------------------------------|----------------------------------------------------|------------------------------|
| `help`    | 查看 CLI 用法、本地命令和服务 Job 的调用方式。                                          | `axonx help`                                       | —                            |
| `start`   | 未指定配置时加载注册的 `default` 配置，启动本机 HTTP 服务。                             | `axonx start`                                      | —                            |
| `start`   | 显式加载指定 YAML 文件启动服务；示例路径相对于 AxonX 仓库根目录，可替换为实际配置文件。 | `axonx start --config axonx/config/default.yaml`   | —                            |
| `exec`    | 列出当前 Python 环境可执行的 Task 注册名及入口类，不执行 Task。                         | `axonx exec`                                       | —                            |
| `exec`    | 在当前进程执行指定 ETL Task 并输出结果，无需通过 HTTP 服务提交。                        | `axonx exec --task a158_etl --start-date 20150101` | —                            |
| `version` | 查询所连接 AxonX 服务的版本信息。                                                       | `axonx version`                                    | `--target 192.168.1.10:1024` |

### 插件管理

- 本地管理：不传 `--target`，直接操作当前 Python 环境。
- 远程管理：传入 `--target`，查询或修改目标服务的插件。
- 检查与构建：源码检查和 wheel 构建在本机完成。
- `plugin inspect` 本地可传源码目录、wheel 路径或已安装插件名；远程只接受目标服务已安装的发行包名或插件名， 例如
  `axonx-alpha158`。不能给本地路径示例直接追加 `--target`，远程检查不会上传源码或 wheel。

| 命令名称           | 具体描述                                                                     | 命令                                                           | 远程参数                     |
|--------------------|------------------------------------------------------------------------------|----------------------------------------------------------------|------------------------------|
| `plugin list`      | 列出当前环境或目标服务已安装的插件；`tasks` 键为 Task 注册名。               | `axonx plugin list`                                            | `--target 192.168.1.10:1024` |
| `plugin show`      | 查看指定插件的版本、注册贡献和依赖等信息。                                   | `axonx plugin show axonx-alpha158`                             | `--target 192.168.1.10:1024` |
| `plugin inspect`   | 检查当前环境或目标服务已安装的插件；参数为发行包名或插件名。                 | `axonx plugin inspect axonx-alpha158`                          | `--target 192.168.1.10:1024` |
| `plugin inspect`   | 从本机源码构建或复用缓存 wheel，检查插件元数据，不安装。                     | `axonx plugin inspect plugins/a158`                            | —                            |
| `plugin inspect`   | 检查本机已有 wheel 的插件元数据，不重新构建或安装；将路径替换为实际文件。    | `axonx plugin inspect '<plugin_wheel_path>'`                   | —                            |
| `plugin build`     | 从源码构建或复用缓存 wheel，输出产物路径、校验值和插件元数据，不安装。       | `axonx plugin build plugins/a158`                              | —                            |
| `plugin build`     | 在指定目录生成 wheel，便于后续分发或安装。                                   | `axonx plugin build plugins/a158 --output .axonx/plugins/dist` | —                            |
| `plugin install`   | 本机从源码构建 wheel 后直接安装；指定远程目标时上传 wheel 并在目标服务安装。 | `axonx plugin install plugins/a158`                            | `--target 192.168.1.10:1024` |
| `plugin install`   | 使用本机已有 wheel 安装；指定远程目标时上传该 wheel 并在目标服务安装。       | `axonx plugin install '<plugin_wheel_path>'`                   | `--target 192.168.1.10:1024` |
| `plugin uninstall` | 从当前环境或目标服务卸载指定插件。                                           | `axonx plugin uninstall axonx-alpha158`                        | `--target 192.168.1.10:1024` |

### 机器

| 命令名称         | 具体描述                                                                  | 命令                                       | 远程参数                     |
|------------------|---------------------------------------------------------------------------|--------------------------------------------|------------------------------|
| `list_machines`  | 查询所连接服务 `targets` 中机器的地址和健康状态，用于选择执行目标。       | `axonx list_machines`                      | `--target 192.168.1.10:1024` |
| `machine_status` | 查询所连接服务所在机器的 CPU、内存和 GPU 信息。                           | `axonx machine_status`                     | `--target 192.168.1.10:1024` |
| `shell`          | 在所连接服务所在机器执行 shell 命令；示例查询当前目录，Job 超时为 30 秒。 | `axonx shell --command 'pwd' --timeout 30` | `--target 192.168.1.10:1024` |

### Task 提交与运行

| 命令名称              | 具体描述                                                                                 | 命令                                                                               | 远程参数                     |
|-----------------------|------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|------------------------------|
| `get_task_definition` | 查询一个 Task 的完整定义；`--task` 填注册名，不是 Task ID 或实例名称。                   | `axonx get_task_definition --task a158_etl`                                        | `--target 192.168.1.10:1024` |
| `submit`              | 提交 ETL Task，由框架生成名称；记录 `answer.task_id`、`answer.run_id` 和 `answer.task`。 | `axonx submit --task a158_etl --start-date 20150101`                               | `--target 192.168.1.10:1024` |
| `submit`              | 使用显式名称生成固定 Task ID；重复使用该名称会在前次完成后替换其产物。                   | `axonx submit --task a158_etl --task-name default --start-date 20150101`           | `--target 192.168.1.10:1024` |
| `submit`              | 使用成功 ETL 的实际 Task ID 作为数据来源，提交训练 Task。                                | `axonx submit --task a158_train --source-tasks '<etl_task_id>'`                    | `--target 192.168.1.10:1024` |
| `wait_task`           | 等待指定 Run ID 结束，返回完整状态；仅 `succeeded` 时响应成功。                          | `axonx wait_task --task-id '<task_id>' --run-id '<run_id>' --client-timeout 86400` | `--target 192.168.1.10:1024` |
| `stream_task`         | 持续输出指定 Task 的进度与日志，直到结束并返回最终状态。                                 | `axonx stream_task --task-id '<task_id>' --stream true`                            | `--target 192.168.1.10:1024` |
| `list_task_ids`       | 列出具有状态文件的 Task ID，供后续查询使用。                                             | `axonx list_task_ids`                                                              | `--target 192.168.1.10:1024` |
| `list_task_statuses`  | 获取 Task 状态快照列表，便于检查多个 Task 的运行情况。                                   | `axonx list_task_statuses`                                                         | `--target 192.168.1.10:1024` |
| `status`              | 获取指定 Task 当前的状态快照，不持续跟踪日志。                                           | `axonx status --task-id '<task_id>'`                                               | `--target 192.168.1.10:1024` |
| `read_task_log`       | 单次读取指定 Task 的日志尾部，默认最多 65536 字节，用于查看最近输出。                    | `axonx read_task_log --task-id '<task_id>'`                                        | `--target 192.168.1.10:1024` |
| `read_task_log`       | 从指定字节偏移读取日志；示例从头读取，后续可用响应的 `next_offset` 继续读取。            | `axonx read_task_log --task-id '<task_id>' --offset 0 --limit 65536`               | `--target 192.168.1.10:1024` |
| `get_task_context`    | 汇总状态、元数据与日志路径、依赖图及上下游关系，供排查或后续研究使用。                   | `axonx get_task_context --task-id '<task_id>'`                                     | `--target 192.168.1.10:1024` |
| `get_task_graph`      | 查询包含指定 Task 的依赖图，检查节点、连线和上下游关联。                                 | `axonx get_task_graph --task-id '<task_id>'`                                       | `--target 192.168.1.10:1024` |
| `cancel`              | 取消正在排队或运行的 Task。                                                              | `axonx cancel --task-id '<task_id>'`                                               | `--target 192.168.1.10:1024` |
| `delete_tasks`        | 删除已结束或仅有元数据的 Task 及其文件；单个 ID 也须用 JSON 数组传入。                   | `axonx delete_tasks --task-ids '["<task_id>"]'`                                    | `--target 192.168.1.10:1024` |
| `delete_tasks`        | 一次删除多个已结束或仅有元数据的 Task 及其文件。                                         | `axonx delete_tasks --task-ids '["<task_id_1>","<task_id_2>"]'`                    | `--target 192.168.1.10:1024` |

### 工作区与同步

| 命令名称         | 具体描述                                                                               | 命令                                                                         | 远程参数                     |
|------------------|----------------------------------------------------------------------------------------|------------------------------------------------------------------------------|------------------------------|
| `list_entries`   | 查询所连接服务的工作区根目录，查看已有 Task 类型目录和其他条目。                       | `axonx list_entries --path ''`                                               | `--target 192.168.1.10:1024` |
| `list_entries`   | 查询指定 ETL Task 目录中的文件和子目录，定位实际产物路径。                             | `axonx list_entries --path 'etl/<etl_task_id>'`                              | `--target 192.168.1.10:1024` |
| `list_task_runs` | 按 Task 类型列出包含 `metadata.json` 的运行目录；示例查询 ETL 类型。                   | `axonx list_task_runs --task-type etl`                                       | `--target 192.168.1.10:1024` |
| `preview_file`   | 读取指定 Task 的 `metadata.json`，检查配置、依赖和产物路径。                           | `axonx preview_file --path 'etl/<etl_task_id>/metadata.json'`                | `--target 192.168.1.10:1024` |
| `preview_file`   | 按行预览 CSV 或 Parquet 数据；示例跳过 200 行，最多返回 100 行，路径须从实际产物取得。 | `axonx preview_file --path '<artifact_path>' --offset 200 --limit 100`       | `--target 192.168.1.10:1024` |
| `delete_entries` | 删除指定工作区文件或目录；单个路径也须用 JSON 数组传入。                               | `axonx delete_entries --paths '["etl/<etl_task_id>/old.csv"]'`               | `--target 192.168.1.10:1024` |
| `delete_entries` | 一次删除多个工作区文件或目录，路径均相对于工作区。                                     | `axonx delete_entries --paths '["<workspace_path_1>","<workspace_path_2>"]'` | `--target 192.168.1.10:1024` |
| `sync_tasks`     | 使用目标服务返回的暂存归档路径，替换归档携带的 Task 目录；该命令本身不上传文件。       | `axonx sync_tasks --path '<staged_archive_path>'`                            | `--target 192.168.1.10:1024` |

- 产物路径：成功运行后，元数据写入 `工作区/<task_type>/<task_id>/metadata.json`；`preview_file` 使用工作区相对路径。
- 实际取值：上传归档路径、目标服务地址和 Task ID 均从真实配置或服务响应取得，再执行对应命令。
