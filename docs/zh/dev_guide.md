# AxonX 开发与运行指南

AxonX 通过类型化 Task 执行量化研究，为 CLI、HTTP、MCP 和 Studio 保存执行证据。本文独立包含安装、开发、部署、执行与检查所需流程。

在用户授权范围内操作，示例本身不授权安装、执行、删除、外部消息或远程变更。使用发现的 Schema 与实际记录，不以进程创建推断成功，不编造不可得结果。

## 环境与服务

macOS 或 Linux 使用 Python 3.12+。安装后端与预构建 Studio，设置独立令牌并启动前台 Daemon/服务：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install 'axonx[studio]'
export AXONX_SERVICE_TOKEN='replace-with-your-service-token'
axonx app --service.host 127.0.0.1
```

保持该终端运行，另一终端使用相同环境和 token。访问 `http://127.0.0.1:1024/`，在 Studio 设置中填写令牌。Demo 无需行情或模型凭据。不带 `studio` extra 的 `axonx` 仅安装后端。

开发框架或插件时，在已激活的环境中使用源码仓库：

```bash
git clone https://github.com/FlowLLM-AI/AxonX.git
cd AxonX
pip install -e '.[dev,studio]'
```

下文源码路径相对仓库根目录；服务工作区路径属于所选执行机器。仅安装 Python 包不会提供示例插件源码。

CLI 启动从工作目录及最多五级父目录查找最近的 `.env`，已有环境变量优先。默认端口 `1024`、工作区 `.axonx`、日志目录 `logs`、时区 `Asia/Shanghai`。自定义启动时，将以下内容保存为 `app.yaml`，用 `axonx app --config app.yaml` 替代默认启动命令：

```yaml
extends: default
workspace_dir: .axonx
log_dir: logs
timezone: Asia/Shanghai
service:
  host: 127.0.0.1
  port: 1024
  token: ${AXONX_SERVICE_TOKEN}
cron: []
```

配置支持 YAML/JSON、`${NAME}`/`${NAME:-default}` 插值和 `extends`。字典递归合并，列表整体替换。运行时相对路径以进程目录为基准，不以配置文件为基准。修改配置后重启服务。

## 发现能力、连接与响应

执行或安装前先发现所选环境的能力：

```bash
axonx --help
axonx help
axonx help --job cli
axonx diagnose
axonx list_task_defs --include-schemas false
axonx get_task_def --task demo
axonx machine_status
axonx python --code 'print(1 + 2)' --timeout 30
```

`--help` 离线显示语法，`help` 查询公开 Job。裸命令 `axonx exec` 列出当前解释器的 Task；定义 Job 使用常驻服务启动时的目录。`diagnose` 报告构建、Python、磁盘/资源和已安装插件，仅显示凭据是否配置，不返回密钥。资源读数不代表自动分配。

`python` 适合短时探测，使用服务解释器、工作目录和环境，在新进程中执行；业务超时默认 30 秒、上限 300 秒，检查 `exit_code`、stdout/stderr 与截断标志。请求结束时清理进程组，长期工作使用 Task 执行/组合。

CLI 直连远程无需本机服务。替换 `node-b:1024`，配置目标令牌，执行、状态和产物查询使用同一目标：

```bash
export AXONX_TARGET_TOKEN='replace-with-target-token'
axonx version --target node-b:1024
axonx get_task_def --task demo --target node-b:1024
axonx exec --task demo --task-name remote-check --x 1 --y 2 --target node-b:1024
```

地址必须带端口，可使用 HTTP(S)，不能包含凭据、子路径或查询字符串。`--token` 覆盖环境凭据。默认本机 CLI 使用 `AXONX_SERVICE_TOKEN`，显式 `--target` 使用 `AXONX_TARGET_TOKEN`；Python 客户端需显式传 token。Studio 经后端配置的 `targets` 地址/令牌转发。

HTTP 使用 Bearer 鉴权，通过 `POST /jobs/NAME` 传入 `arguments` 和可选的已配置转发 `target`。例如，向 `/jobs/cli` 发送：

```json
{
  "arguments": {
    "argv": [
      "exec",
      "--task",
      "demo",
      "--task-name",
      "http-check",
      "--x",
      "1",
      "--y",
      "2"
    ]
  }
}
```

普通响应为 `{answer, success, metadata}`。`cli` 的 answer 包含 `stdout`、`stderr`、`exit_code`、`stdout_truncated`、`stderr_truncated`，各通道最多保留前 1 MiB。HTTP 200 或状态查询成功不代表 Task 成功。CLI Job 成功/失败返回 0/1，非法 CLI 输入通常返回 2。

MCP 通过 `/mcp` 的 Streamable HTTP 暴露公开 Job 名称与 Schema，返回普通 Job 响应；先发现实际服务工具。未配置服务令牌时，不公开要求认证的 Job。实时事件使用 `POST /jobs/NAME/events`，SSE 类型为 `progress`、`log`、`artifact`、`agent_message`、`result`，只有终态 result 确定 Job 结果。CLI 可用 `--stream true --stream-format json` 输出逐行事件。

## 执行、身份与观察

参数使用 `--field value`：连字符转下划线，点号生成嵌套字典，值转换布尔值、null、数字和 JSON。shell 中引用含 `#` 的 Task ID 和 JSON 数组。未声明的 Task 入参会被拒绝。

```bash
axonx exec --task demo --task-name check --x 1 --y 2
axonx status --task-id 'base#demo#check' --detail full
axonx wait_task --task-id 'base#demo#check' --client-timeout 600
axonx read_task_log --task-id 'base#demo#check' --offset -1 --limit 8192
axonx stream_task --task-id 'base#demo#check' --stream true
```

本地 `exec` 在 CLI 进程中同步执行，输出业务结果（此处 `result=3`）并返回 Task 退出码，不返回提交句柄。显式指定 target 时，由服务 `cli` Job 持有子进程组并持续传输输出至退出。远程原生命令保留子进程退出状态，负信号码映射为 `128 + signal`。

Task ID 为 `task_type#registration#task_name`；类型包括 `base`、`api`、`etl`、`analysis`、`train`、`predict`、`inference`、`backtest`。实例名为 1–32 个字母、数字或连字符，省略时自动生成。metadata `started_at` 区分同一目录的多次执行。状态为 `running`、`succeeded`、`failed`。

CLI 的 `status`、`wait_task` 默认返回摘要，`--detail full` 返回输入、输出、步骤与子调用。`wait_task` 捕获当前启动时间，等待期间若被替换则报错。`read_task_log --started-at TIMESTAMP` 保护日志读取；游标按字节计，用 `next_offset` 续读。列表/图使用周期刷新的索引（默认 5 秒），单任务状态直接读取 metadata。`get_task_context` 返回完整选中元数据、路径与输入关系，不是按字节限制的摘要。

执行配置优先级为显式 CLI 字段 > 服务 `get_config` > 默认值。共享字段为 `workspace_dir`、`log_dir`、`timezone`、`execution_target`、`log_to_console`、`log_to_file`、`environment`，显式环境变量按键合并。只有连接失败允许回退；认证或配置非法会失败。工作区覆盖只影响该命令，服务查询仍观察服务工作区。客户端默认超时 60 秒，`--client-timeout` 与业务截止时间分开。

命令连接中断后先检查 Task 记录再重试。取消远程命令或关闭其服务可能终止所属进程组；取消观察流不会停止被观察 Task。

## 开发并打包 Task

创建以下最小插件，`__init__.py` 可为空：

```text
example/
  pyproject.toml
  example_plugin/
    __init__.py
    plugin.yaml
    task.py
```

将 Task 写入 `example_plugin/task.py`：

```python
from axonx.task.core.base import BaseTask
from axonx.task.models.params import BaseInputParams, BaseOutputParams

class AddInput(BaseInputParams):
    x: int
    y: int

class AddOutput(BaseOutputParams):
    total: int

class AddTask(BaseTask):
    """Add two integers and publish their sum."""
    input_cls = AddInput
    output_cls = AddOutput

    def build_task_steps(self):
        yield self.add

    def add(self):
        self.state["total"] = self.input_params.x + self.input_params.y

    def build_output_params(self):
        return AddOutput(total=self.state["total"])
```

将注册写入 `example_plugin/plugin.yaml`：

```yaml
tasks:
  example_add: example_plugin.task:AddTask
```

将包元数据写入 `pyproject.toml`：

```toml
[build-system]
requires = ["setuptools>=84.0.0"]
build-backend = "setuptools.build_meta"

[project]
name = "axonx-example"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["axonx>=0.3.0"]

[project.entry-points."axonx.plugins"]
example = "example_plugin"

[tool.setuptools.package-data]
example_plugin = ["plugin.yaml"]
```

从包含 `example/` 的目录执行：

```bash
axonx plugin install -e ./example
axonx exec --task example_add --task-name check --x 1 --y 2
```

结果为 `total=3`。分发包 `axonx-example`、入口名 `example`、Task 注册名 `example_add` 各有用途。注册名必须唯一，manifest 只接受 `tasks`；运行时资源须包含在 package data 中。应用 Component/Job 通过独立的 `Application(providers=...)` 组合与配置扩展。类 docstring 提供定义说明。

`BaseTask` 默认类型为 `base`，研究子类选择对应类型。输入/输出继承 `BaseInputParams`/`BaseOutputParams`，拒绝未声明字段。步骤必须同步，返回 `output_cls` 实例而非字典。`self.state` 在惰性生成的步骤之间传值。输出写入 `self.task_dir`，累计业务状态写入 `self.persistent_dir`，研究输入路径通过 `self.resolve_workspace_path()` 解析。

`TaskExecutor` 负责准备、身份、进度、metadata 与终态。在步骤结束或初始化失败后调用 `close()`，清理后构建最终输出；保留输出构建所需的数据。`report_progress()` 更新当前步骤或命名子步骤，结束前停止后台生产者。`publish_output()` 发布经校验的部分输出，输出构建器须可重复调用。原子写入与快照工具位于 `axonx.task.storage.files`。

任意 Task 都可用 `self.run_task("demo", node_name="add", x=1, y=2)` 同步调用子任务。`ChildTaskResult` 提供 `success`、`child_task_id`、调用 `record`、类型化 `output_params` 和 JSON `output`；构造失败时 ID/输出可能不可用。子任务共享进程、工作区、时区与业务时钟，默认继承父实例名，可用 `task_name` 覆盖。`node_name` 标识调用次数，不隔离目录。重复注册名/实例名会替换已结束输出，须先消费或固定产物。默认 `on_error="stop"` 抛错；`continue` 允许后续工作，但父任务默认仍保留失败结果。

用唯一的 JSON 数组 `upstream_task_ids` 声明输入依赖，CLI `exec` 也接受逗号分隔 ID。各子任务的依赖须显式传入。`get_task_graph` 仅据这些输入引用建边，`missing` 表示记录不可用，`provisional` 表示记录存在但尚未 `succeeded`；父子调用单独保存在 `parent_task_id`/`children`，包含关系与调用顺序都不会增加输入边或调度 DAG。

## 安装、部署与刷新插件

从仓库按依赖顺序安装参考插件，仅选择所需层：

```bash
axonx plugin install -e ./plugins/qlib_a158
axonx plugin install -e ./plugins/qlib_factor
axonx plugin install -e ./plugins/qlib_strategy
axonx plugin list
axonx plugin build ./plugins/qlib_a158 --output ./dist/plugins
```

`plugin` 不带 target 时操作当前 Python 环境，指定 target 后在服务解释器中执行。`show`/`uninstall` 接收分发包名或入口名，`inspect` 还接受源码目录或 wheel。源码检查/构建生成 wheel 元数据，不安装。保留返回的 `wheel`、`sha256`、`content_sha256`；两个哈希分别标识 wheel 字节与规范化内容。

editable 安装要求执行机器上已有源码，不能与 `--output` 同用。普通安装构建源码或使用已有 wheel，安装 AxonX 自身之外的依赖并核验来源。安装或源码变化后重启常驻服务；依赖/入口点变化后重新安装。新 CLI 进程重新发现插件，已有进程不固定版本，也不自动刷新。环境变更需自行协调。

`--target` 将所有原生命令路径解释为目标机路径，不传输本地文件。本地到远程部署按本地构建、上传 `/upload`、安装绝对 `location`、清理相对 `path`、重启验证完成。以下完整上传/安装/清理示例中的 wheel 文件名、地址和 token 须替换为实际值：

```python
import asyncio
import hashlib
import json
import os
from pathlib import Path
from axonx.client.http import HttpClient

async def deploy():
    wheel = Path("dist/plugins/ACTUAL_FILENAME.whl")
    expected = hashlib.sha256(wheel.read_bytes()).hexdigest()
    async with HttpClient(
        target="http://node-b:1024",
        token=os.environ["AXONX_TARGET_TOKEN"],
        timeout=600.0,
    ) as client:
        uploaded = await client.copy_file(wheel)
        try:
            response = await client.run_job("cli", {
                "argv": ["plugin", "install", uploaded.location],
            })
            result = response.answer
            if not response.success or result["exit_code"] != 0:
                raise RuntimeError(str(result))
            installed = json.loads(result["stdout"])
            if installed["sha256"] != expected:
                raise RuntimeError("Installed wheel differs from local wheel")
            print(installed)
        finally:
            await client.discard_file(uploaded.path)

asyncio.run(deploy())
```

`POST /upload` 也接受带 `x-file-name` 的二进制内容，或 multipart `file` 与可选 `directory`，`x-file-directory` 优先。暂存范围为工作区 `tmp`。`StagedFile` 包含相对 `path`、绝对 `location`、字节 `size`，不返回校验和。`DELETE /upload?path=...` 清理暂存。默认传输预算 512 MiB，multipart 额外允许 64 KiB 封装。清理不会回滚安装。

安装后请求重启，等待服务可连接，检查更新完成后再查询定义：

```bash
axonx restart_service --target node-b:1024
axonx get_update_status --target node-b:1024
axonx list_task_defs --include-schemas false --target node-b:1024
axonx get_task_def --task qlib_a158_etl --target node-b:1024
```

重启返回已接受操作的 `update_id`，用 `get_update_status --update-id ID` 跟踪该操作，不仅依赖最近记录。安装失败或连接中断可能留下部分环境变更，重试前先核验已安装元数据。

## 执行与改进研究

参考主链为 ETL → Train → Predict → Backtest，因子分析通过 `qlib_a158_factor` 从 ETL 独立分支。先安装 `qlib_a158` 并准备足够的 Tushare 历史。数据令牌与 AxonX 服务令牌不同；兼容数据服务可额外配置 `AXONX_TUSHARE_BASE_URL`。

以下选择一个历史示例窗口。各命令分别执行，确认退出码与完整 metadata 后再运行下一阶段，脚本须遇错停止。已有完整原始历史时可复用，不必重新下载：

```bash
export AXONX_TUSHARE_TOKEN='replace-with-data-token'
axonx exec --task download_tushare_task --task-name data-01 \
  --start-date 20140101 --end-date 20240131
axonx exec --task qlib_a158_etl --task-name research-01 \
  --start-date 20150101 --end-date 20240131
axonx exec --task qlib_a158_train --task-name research-01 \
  --upstream-task-ids '["etl#qlib_a158_etl#research-01"]' \
  --train-start 20150101 --train-end 20230101
axonx exec --task qlib_a158_predict --task-name research-01 \
  --upstream-task-ids '["train#qlib_a158_train#research-01","etl#qlib_a158_etl#research-01"]' \
  --pred-start 20230101 --pred-end 20231231
axonx exec --task qlib_a158_backtest --task-name research-01 \
  --upstream-task-ids '["predict#qlib_a158_predict#research-01"]' \
  --top-ns '[20,30]' --buy-cost-rate 0.0005 --sell-cost-rate 0.0015
```

下载写入共享 `tushare/` 分区，位于下载 Task 目录之外。默认回溯 7 天不足以支持多年训练和滚动特征。检查覆盖和数据权限，空/缺失行情不能视为零收益。

训练结束日期不包含在训练区间，先用时间验证选择轮数再重拟合。预测开始不得早于训练结束，使用保存的特征顺序，输出评分而非收益预测。预测和选股输入不能关联未来标签。

也可执行已安装的父 Task，由它管理子名称与依赖，返回 `stage_task_ids`：

```bash
axonx exec --task qlib_a158_research --task-name pipeline-01 \
  --etl.start-date 20150101 --train.train-end 20230101 \
  --predict.pred-end 20231231 --analysis '{}'
```

此处 `analysis: {}` 启用因子分析，省略则禁用；预测开始默认采用训练结束日期。父入参拒绝调用方指定子名称、依赖及显式回测输入文件。复用已有上游时使用叶子 Task。远程研究每步保持相同 target，路径和凭据属于该机器。

仅重跑假设所需部分：修改特征通常从 ETL 开始，修改模型可复用兼容 ETL，修改组合可复用兼容预测。`qlib_factor` 增加 13 个可选特征，但训练默认仍用 158 个基线特征；`qlib_strategy` 复用预测并提供持有期、排名与换仓策略。控制比较时固定数据、标签、窗口、训练参数、成本和股池定义。在开发窗口筛选候选，用独立确认窗口评估锁定的方案。

## 产物与研究契约

研究基类位于 `axonx.task.core.research`，输入/输出模型位于 `axonx.task.models.params`，可移植协议位于 `axonx.task.models.artifacts`。自定义 Task 可直接继承 `BaseTask`。标准基类输出要求：

| 阶段     | 基类必填字段                                             |
| -------- | -------------------------------------------------------- |
| ETL      | `rows`、`date_range`                                     |
| Analysis | `rows`；可选分组 `scores`                                |
| Train    | `train_rows`；可选 metrics、parameters、`training_curve` |
| Predict  | `rows`、`date_range`、预测 `protocol`                    |
| Backtest | `default_universe`、非空 `universes`、回测 `protocol`    |

`ArtifactRecord` 位于 `axonx.task.models.artifacts`，`artifact_record` 和 `verify_artifact` 来自 `axonx.task.storage.artifacts`。所有输出包含 `artifacts: dict[str, ArtifactRecord]`。先写文件，再发布 metadata。`artifact_record(path, task_dir)` 记录 Task 内相对 `path`、字节 `size`、`revision="<size>:<mtime_ns>"`。用 `verify_artifact(root, record)` 核验普通文件的大小/版本，仅解析路径不会核验。此版本不是内容哈希，无法发现大小和修改时间均未变化的内容修改。通过原子替换发布不可变文件，字段须从真实文件计算。

`upstream_artifact(task, task_id, name)` 要求成功且非副本的来源，并核验一个产物；`pin_upstream_artifacts(task, task_id, *names)` 将经核验文件固定到消费者 `inputs/`；`snapshot_model_collection()` 核验并复制模型集合。这些 helper 位于 `axonx.task.storage.inputs`。业务兼容性和特征时点仍由消费者负责。

协议头要求整数 `version=1` 和生产者 `task_type`，拒绝不支持或缺失的协议头。Qlib 训练通过 `artifacts.model_manifest` 指向 `models.json`；`ModelCollection` 包含 `feature_protocol`、命名 `members`（`model_artifact`、`model`）和产物注册表。模型清单是 Qlib 消费者要求，不是 `BaseTrainOutputParams` 必填字段。特征语义与指纹属于插件。

`PredictionProtocol` 要求非空 `model_identity: dict[str, str]`、排序去重的 `dates`、非空且不同的成员到列映射 `score_columns`、`predictions_revision`。Qlib 身份项为 `models_sha256`/`features_sha256`，预测通过 `artifacts.predictions` 注册。日期范围使用 `start`/`end`。训练曲线使用字符串 `x` 标签，以及有限数值、等长的 `y_left`/可选 `y_right`；非空曲线须有左轴序列，两轴名称不能重复。

股票 ETL 分离 `dataset`、`labels`、`market`、`calendar`。预测行要求唯一 `(trade_date, trade_time, ts_code)` 主键，以及有限 `pred`、Boolean `is_model_candidate`/`is_buyable_at_signal`、`signal_price`、`signal_adjustment_factor`，不包含未来标签。回测还需独立行情/日历产物，可选标签用于信号诊断。评估前固定输入版本。

股票回测插件继承 `axonx.task.builtins.stock.backtest.BaseStockBacktestTask`，实现 `build_universes()` 和返回唯一信号主键的 `select_universe(signals, universe)`。各股池独立发布日期、维度、评估状态与产物角色引用，daily/summary 角色指向输出根级产物注册表，`default_universe` 选择默认报告。发布 `signals_format="stock-signals-v1"`，`signals.parquet` 保留信号并增加 `is_backtest_candidate`、`target_rank`、`label_return`。真实成交、现金、持仓、交易和订单与信号目标不同。说明执行/估值时点、费用、缺失行情处理和收益单位；Task 成功不证明评估完整或策略盈利。

## 工作区、重跑与清理

目录规则为 `<workspace>/<task_type>/<task_id>/`：

```text
.axonx/
  base/base#demo#check/
    metadata.json
    events.jsonl
    persistent/
  etl/etl#qlib_a158_etl#research-01/
  tushare/
  tmp/
  agent/
logs/
```

`metadata.json` 保存当前身份、进程归属、生命周期、输入/输出、步骤和子调用，`events.jsonl` 记录当前进度事件。`log_path` 指向真实文本日志，可位于 Task 目录外。产物路径相对 Task 目录，`preview_file` 路径相对工作区。

```bash
axonx list_task_statuses --task-type etl --state succeeded
axonx get_task_graph --task-id 'base#demo#check'
axonx list_entries --path ''
axonx list_task_directories --task-type base
axonx preview_file --path 'base/base#demo#check/metadata.json' --max-bytes 8192
axonx kill --task-id 'base#demo#check' --timeout 5 --force false
axonx delete_entries --paths '["base/base#demo#check"]'
```

停止与删除是独立操作，最后一条仅示例清理已核验停止的目录。`kill` 检查机器/PID/进程启动身份，进程内子任务会解析到根所有者。`execution_target` 声明可达的源服务，须带端口，拒绝回环/通配地址；它与源 `workspace_dir` 支持远程停止，`machine_id` 是身份而非地址。

同名重跑先确认旧进程停止，再替换当前文件并保留 `persistent/`。Task 目录不提供协调锁，启动、删除和副本替换须串行化。活动、异机或无法验证的 running 记录会阻止替换。查询不收敛失效记录，运行准备或显式 kill 可收敛已确认退出的本机进程。删除不保护活动 Task，并移除保留数据。

目录列表最多返回 5000 个排序条目，`truncated` 时以 `offset + entries.length` 继续。行预览使用 `offset`、`limit`、`has_more`，服务端默认 200 行、上限 5000，CLI 默认 20。文本/Markdown 默认 512 KiB，JSON/YAML 最多 32 MiB。CLI 增加 `max_bytes=8192`，截断 JSON/YAML 返回原文和解析错误。JSONL 具有独立的 512 KiB 页预算。得出结论前检查实际行、解析错误与截断。

## 展示同步与备份

展示同步复制有限证据，不复制可执行环境。普通选择包含终态 Task，`live_task_ids` 可选父任务组及其精确子执行快照；`task_names` 筛选 Task ID 末段，空列表包含所有名称。源端可使用以下可选 `sync.yaml`，替换实际目标与令牌：

```yaml
extends: default
targets:
  - address: http://node-b:1024
    token: ${AXONX_TARGET_TOKEN}
components:
  sync:
    default:
      backend: local
      target: http://node-b:1024
      task_index: default
      task_names: []
      live_task_ids: []
jobs:
  sync_flush:
    parameters: { type: object, properties: {}, additionalProperties: false }
    steps:
      - backend: sync_flush_step
        sync: default
```

通过 `axonx app --config sync.yaml` 启动，再显式调用 `axonx sync_flush`，默认配置未启用该 Job。组件对账变更、构建/上传归档并调用 `sync_tasks`，`task_sync_index` 返回经核验的目标快照。已有合法展示归档也可经 `/upload` 暂存，将相对 `path` 传给 `sync_tasks`，并可附带 Task 目录 `deletions`。

发送/接收使用较小传输预算，默认 512 MiB。大型按日期分组的 Parquet 可被采样，省略文件记录于 `replica.omitted`，保留文件记录于 `replica.files`。实时快照绑定源、根 Task/启动时间和有序 revision。副本不能执行、不能作为本地 kill 目标或研究输入；同步不能覆盖活动原始 Task。

备份前停止或协调写入，保留完整 Task 目录、`persistent/`、原始数据、外部日志、Agent 状态、配置、源码/插件版本和依赖。恢复文件不会恢复进程。展示副本可省略输入、模型和原始数据，不能代替完整备份。

## 定时运行与维护

定时执行本机任务时，将以下内容保存为 `scheduled.yaml`，用 `axonx app --config scheduled.yaml` 启动：

```yaml
extends: default
timezone: Asia/Shanghai
cron:
  - expression: "0 16 * * 1-5"
    command: "axonx exec --task download_tushare_task --days-back 7"
```

计划仅接受五个数值 cron 字段与本地 `axonx exec --task NAME`，不经 shell 解析；不支持管道、重定向或 `--target` 等客户端选项。触发使用应用时区，不回放错过时点。继承列表整体替换，`cron: []` 禁用计划，修改后重启。没有内置跳过/替换重叠策略，自动实例名保留不同记录，固定名称须自行协调。

服务计算触发时点，Daemon 持有已启动的定时命令。服务拥有的手动 CLI 命令随服务停止，Daemon 定时执行在服务重启期间继续。Daemon 不恢复或重跑已完成 Task。通过 Task metadata 和 `logs/cron/entry-N.log` 检查结果。

```bash
axonx restart_service
axonx get_update_status
```

`restart_service` 重载配置与已加载代码；`update_from_git` 快进当前分支、构建/安装 AxonX 与 Studio 后替换服务；`update_from_pip` 升级发布包。每次选择一种操作，均要求认证且由 Daemon 启动，不接受 `force`。响应仅表示接受，保留 `update_id`，重连后调用 `get_update_status --update-id ID` 至 `succeeded` 或 `failed`。维护期间除版本/更新状态查询外拒绝新本地工作。部分源码/依赖变更不会回滚，就地更新也不为运行中的定时 Task 固定版本。监督器或启动命令变化需重新启动整个 Daemon。

## 窗口任务、在线历史与回放

`axonx.task.core.windows` 提供 `BaseWindowTask`、`BaseRealtimeApiTask`、`BaseInferenceTask`，输入为 `models.params` 中的 `ExecutionWindow`/`WindowInputParams`，结果为 `models.reports` 中的 `WindowResult`。窗口 key 唯一，起止时间带时区并按开始时间排序，要求 `end_at > start_at`。

通用窗口实现 `execute_window(window, budget)`，实时采集实现 `collect(window, budget)` 并返回 `None` 继续轮询；推理实现 `initialize_run()`、`inputs_ready(window)`、`infer(window, budget)`，初始化时固定一份非空模型身份映射。在 `close()` 释放资源。逐个结果以业务状态 `done`、`skipped`、`incomplete`、`failed` 发布，与 Task 状态分开；incomplete/skipped 默认不使整个 Task 失败。

用 `axonx.task.core.clock` 的 `DeadlineBudget.remaining_seconds`、`sleep()`、`check()` 约束外部超时、重试和发布；它不能中断任意阻塞操作。异常保留前面窗口结果并停止 Task。

`axonx.task.storage.online.OnlineStore` 将按角色组织的不可变文件写入 `persistent/online/commits/<commit_id>/`，原子更新 `persistent/online/` 下的 `manifest.json`。commit 记录 Task/启动身份、信号日期/时间、revision、模型身份、协议和产物。策略身份变化须使用新实例。用 `read_online_history()` 读取完整/冻结历史，消费前通过 `pin_online_history()` 核验并固定；未被引用的文件不是已提交证据。

`axonx.task.storage.replay.ReplayStream.create()` 固定事件文件并在新目录发布 `stream.json`，拒绝覆盖；打开时核验引用版本。向 Task 注入 `axonx.task.runtime.replay.ReplayClock`，使用 `ReplayCursor` 按带时区的 `available_at` 交付事件，严格早于截止时间。只有创建线程可推进回放时间，生命周期时间戳与执行耗时仍为真实时间。

## 内置 Agent 会话

外部 Agent 使用宿主模型凭据和上文 CLI/MCP 连接。默认内置后端为 Claude Agent SDK，在服务机器配置模型环境后重启：

```dotenv
CLAUDE_CODE_API_KEY=replace-with-model-key
CLAUDE_CODE_BASE_URL=https://api.anthropic.com
CLAUDE_CODE_MODEL_NAME=replace-with-model-name
```

打开 Studio Agent 页面，或调用：

```bash
axonx agent_chat --message 'List current workspace tasks and summarize their actual status.' --stream true --client-timeout 600
axonx list_agent_sessions --limit 20
```

保存 `metadata.session_id`，后续轮次传入 `--session-id UUID`。`get_agent_session` 读取历史，`rename_agent_session`、`tag_agent_session`、`fork_agent_session`、`delete_agent_session` 管理会话；不能删除运行中会话。`cancel_agent_turn --session-id UUID` 中断该轮次，独立研究执行须用 Task `kill` 停止；结束轮次也可能影响它拥有的工具。

SDK `cwd` 默认工作区，源码开发时将 `components.agent.default.cwd` 设为仓库绝对路径。默认 `load_dev_guide=true` 加载应用 `language`（`en`/`zh`）选择的随包指南。`job_tools` 默认空，配置后通过进程内桥接调用对应 Job；SDK 文件/命令工具和权限独立，默认 `bypassPermissions` 并非只读模式。AxonX 管理会话 UUID/续接，同一会话轮次串行。会话存储与 Task 产物、展示同步分开。

## 验证与报告

源码变更在临时工作区运行受影响测试，基础框架检查为 `python -m pytest tests`，插件检查如 `python -m pytest plugins/qlib_a158/tests`。研究测试需安装对应依赖，外部服务测试须显式准备。构建/安装成功不证明算法正确。

完成时报告执行目标/工作区、源码/插件版本或 wheel 哈希、Task ID 与 `started_at`、终态、输入修订、产物、指标及定义。性能结论包含数据/窗口对齐、样本数、成本、缺失数据影响与独立确认情况。失败或执行不确定时报告实际错误、已完成阶段和未验证部分，报告中不放凭据或私有数据。
