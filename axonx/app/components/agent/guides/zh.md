# AxonX 开发与运行指南

You define the question; the Agent implements it; AxonX manages execution and evidence.

用户定义研究问题，Agent 实现代码并验证想法，AxonX 管理 Task 执行、日志、依赖记录和产物。按以下闭环工作，已有条件满足时直接复用：

**定义问题与基线 → 准备执行环境 → 开发插件 → 安装部署 → 运行与检查 → 比较结果并迭代。**

本文按开发和运行顺序组织，通过 `axonx` 命令完成操作。源码路径相对源码仓库根目录，工作区路径属于实际执行机器；示例名称、地址、日期和文件名应替换为当前实验的值。在用户授权范围内操作，不输出凭据，不编造运行结果。

## 0. 定义研究问题

先从用户要求和现有记录中确定：

- **假设与基线**：要验证什么，与哪个实现或参数组比较。
- **实验设置**：数据源、股池、信号可用时点、训练/验证/评估窗口、成本与成交假设。
- **判断方式**：主要指标、候选选择规则、时间与资源预算。

缺少影响实现或结论的条件时再澄清。因子分析、模型实验、策略回测可以独立开展，不必每次运行完整研究链。固定比较所需的控制变量，在开发窗口筛选候选，用独立确认窗口评估锁定方案；负面结果也可以完成验证。

## 1. 准备执行环境

区分编辑源码的开发机与运行 Task 的执行机，它们可能是不同机器。

| 当前条件            | 操作                                                 |
| ------------------- | ---------------------------------------------------- |
| 已有本地或远程服务  | 复用连接、凭据和工作区，先发现能力；无需重新启动服务 |
| 只需本机运行 Task   | 安装后端即可使用本地 `exec`，无须启动服务            |
| 需要新服务或 Studio | 安装后启动 `axonx app`；Studio 按需安装              |

### 安装与启动（需要时）

macOS/Linux 使用 Python 3.12+。新建环境并安装后端：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install axonx
```

需要 Studio 时安装带预构建界面的版本：

```bash
pip install 'axonx[studio]'
```

启动本地服务：

```bash
export AXONX_SERVICE_TOKEN='replace-with-your-service-token'
axonx app --service.host 127.0.0.1
```

保持终端运行，另一终端使用相同环境和 token。已安装 Studio 时访问 `http://127.0.0.1:1024/`，在设置中填写令牌。仅开发插件不要求 Node.js 或内置 Agent 的模型凭据。

需要参考插件源码时克隆仓库；已有检出目录则复用。Python 安装包不包含这些示例项目：

```bash
git clone https://github.com/FlowLLM-AI/AxonX.git
cd AxonX
pip install -e '.[dev]'
```

默认端口 `1024`、工作区 `.axonx`、日志目录 `logs`、时区 `Asia/Shanghai`。CLI 加载当前目录及最多五级父目录中最近的 `.env`，保留已有环境变量。自定义配置示例：

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

保存为 `app.yaml` 后启动：

```bash
axonx app --config app.yaml
```

自定义文件只有声明 `extends: default` 才继承默认配置；映射递归合并，列表/标量替换，支持环境变量插值。相对路径以进程工作目录为基准，配置修改后重启服务。

### 连接与能力发现

```bash
axonx --help
axonx help
axonx help --job status
axonx diagnose
axonx get_config
axonx exec
axonx list_task_defs --include-schemas false
axonx get_task_def --task demo
```

`--help` 离线显示 CLI 语法；`help` 列出服务可用命令，`help --job status` 查看 `status` 的详细参数与返回格式。不带参数的 `exec` 列出当前解释器的 Task，查询命令需要连接服务。`list_task_defs`/`get_task_def` 查看服务加载的 Task 及输入/输出 Schema。`diagnose` 检查版本、Python、插件和资源；`get_config` 确认工作区和执行环境，其中可能包含敏感配置，不要原样放入报告。

连接远程服务只需开发机安装 CLI，无需在开发机启动服务：

```bash
export AXONX_TARGET_TOKEN='replace-with-target-token'
axonx version --target node-b:1024
axonx help --target node-b:1024
axonx diagnose --target node-b:1024
axonx get_task_def --task demo --target node-b:1024
```

显式 `--target` 使用 `AXONX_TARGET_TOKEN`，默认本地连接使用 `AXONX_SERVICE_TOKEN`；`--token` 可覆盖。地址须带端口，可使用 HTTP(S)，不能包含凭据、子路径或查询字符串。执行、查询和文件读取始终使用同一目标。

需要确认执行机资源或 Python 环境时运行，远程机器加相同 target：

```bash
axonx list_machines
axonx machine_status
axonx python --code 'import sys; print(sys.executable)' --timeout 30
```

`list_machines` 检查已配置目标的连接；`machine_status` 查看资源，资源读数不代表自动分配；`python` 使用服务解释器运行短时探测，默认 30 秒、上限 300 秒。长期计算写成 Task。

## 2. 开发或修改插件

先阅读相关插件的 README、`pyproject.toml`、`plugin.yaml`、Task 实现与测试，再选择实现方式：

| 需求                 | 实现与参考                                                               |
| -------------------- | ------------------------------------------------------------------------ |
| 已有参数足以验证     | 复用已安装 Task，直接进入运行阶段                                        |
| 修改现有算法         | 在职责对应的插件中修改，更新参数、测试与说明                             |
| 独立算法或可复用扩展 | 新建插件，注册唯一 Task 名；可位于 AxonX 仓库之外                        |
| 参考完整研究链       | `plugins/qlib_a158/`：ETL、分析、训练、预测、回测与父 Task               |
| 扩展特征或组合规则   | `plugins/qlib_factor/` 扩展 ETL/Train；`plugins/qlib_strategy/` 扩展回测 |

### 最小插件

目录如下，`__init__.py` 可为空：

```text
example/
  pyproject.toml
  example_plugin/
    __init__.py
    plugin.yaml
    task.py
```

`example_plugin/task.py`：

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

`example_plugin/plugin.yaml`：

```yaml
tasks:
  example_add: example_plugin.task:AddTask
```

`example/pyproject.toml`：

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

分发包名 `axonx-example` 用于安装管理，入口名 `example` 标识插件，注册名 `example_add` 用于执行。manifest 只注册 `tasks`，运行所需文件须包含在 package data 中；业务依赖写入 `dependencies`。

### Task 与产物约定

- 输入/输出继承对应 Pydantic 模型，未声明的 Task 入参会被拒绝。步骤同步执行，通过 `self.state` 传值，`build_output_params()` 返回 `output_cls` 实例。
- 输出文件写入 `self.task_dir`，跨同名重跑保留的状态写入 `self.persistent_dir`；研究输入路径使用 `self.resolve_workspace_path()`。用 `report_progress()` 报告进度，在 `close()` 中释放资源；输出在清理后构建，须保留所需状态。
- 用 `upstream_task_ids` 声明数据依赖，它不会自动执行上游。用 `self.run_task(...)` 同步调用子任务，并检查返回的 `success`、`child_task_id` 和类型化 `output_params`。父子调用与输入依赖是两种关系。
- 子任务共享进程与工作区，默认继承父实例名；同一注册名和实例名会复用同一目录，多次调用需使用不同 `task_name` 或先固定产物。

按模型同步时复用模型 `task_name`、子调用逻辑 `node_name` 和进度 `name`/`group`。模型子节点以模型名和连字符开头，哈希 Task 目录显式提供逻辑节点名；共享调用保留默认注册节点名。同步 `rules` 将工作流注册名映射到 `live` 或 `terminal`，`model_names` 使用通配模式筛选模型。两种模式发布同一套精确任务树，terminal 规则等待任务树结束。

研究基类在 `axonx.task.core.research`，输入/输出在 `axonx.task.models.params`，协议在 `axonx.task.models.artifacts`。标准研究输出的主要必填字段：

| 阶段           | 字段                                             |
| -------------- | ------------------------------------------------ |
| ETL / Analysis | ETL：`rows`、`date_range`；Analysis：`rows`      |
| Train          | `train_rows`                                     |
| Predict        | `rows`、`date_range`、`protocol`                 |
| Backtest       | `default_universe`、非空 `universes`、`protocol` |

先写文件，再用 `axonx.task.storage.artifacts.artifact_record(path, task_dir)` 注册到输出 `artifacts`；记录包含 Task 相对路径、大小和 revision。原子写入与快照复用 `axonx.task.storage.files`。`verify_artifact()` 核验文件，revision 是大小/修改时间标识，并非内容哈希。`axonx.task.storage.inputs` 的 `pin_upstream_artifacts()` 可核验并固定成功、非副本上游的产物；业务兼容性仍由插件检查。

复用协议时使用 `version=1` 和正确的 `task_type`。Qlib 训练发布模型清单，预测发布模型身份、日期、评分列与输入修订；股票 ETL 分离数据、标签、行情和日历，预测不能含未来标签。股票回测可继承 `axonx.task.builtins.stock.backtest.BaseStockBacktestTask`，实现 `build_universes()` 与 `select_universe()`，沿用信号、股池、成交和估值协议，勿另造不兼容格式。

在临时工作区运行受影响测试，再做小范围实际运行：

```bash
python -m pytest plugins/qlib_factor/tests
```

新增插件使用自己的测试目录；框架修改运行相关框架测试，基础套件为 `python -m pytest tests`。研究依赖及外部服务需按测试要求准备。

## 3. 安装与部署插件

先检查 diff，记录源码提交号及未提交改动、插件版本或构建哈希。需要提交源码时按用户要求和项目约定处理；Git 提交不能代替在执行环境安装插件，也不要求先发布到 PyPI。

### 本地安装

从包含 `example/` 的目录执行：

```bash
axonx plugin inspect ./example
axonx plugin install -e ./example
axonx plugin show axonx-example
axonx exec --task example_add --task-name check --x 1 --y 2
```

确认退出码为 0、输出 `total=3`，并检查 `base#example_add#check` 的 metadata。参考插件先安装 `qlib_a158`，再按需安装 factor 或 strategy，两者各自依赖基线插件：

```bash
axonx plugin install -e ./plugins/qlib_a158
axonx plugin install -e ./plugins/qlib_factor
axonx plugin install -e ./plugins/qlib_strategy
axonx plugin list
axonx plugin build ./plugins/qlib_a158 --output ./dist/plugins
```

不带 target 的 `plugin` 操作当前 Python 环境。`inspect`/`build` 只检查/构建，不安装；保留实际 `wheel`、`sha256` 和 `content_sha256`，分别用于定位 wheel、标识文件字节与规范化内容。安装器安装插件依赖但不升级 AxonX 自身，需确认框架版本满足要求；pip 不会自动定位相邻插件源码。

editable 要求执行机已有源码目录，不能与 `--output` 同用。依赖或入口点变化后重新安装；常驻服务在安装或已加载源码变化后需重启，新 CLI 进程会重新发现插件。环境变更应与运行中的研究协调，已有进程不会固定插件版本。

### 远程部署

`--target` 在目标机执行命令，不上传本地文件。目标机已有源码/wheel 时可直接安装；从开发机部署则先构建和上传：

```bash
axonx plugin build ./example --output ./dist/plugins
curl --fail-with-body \
  --header "Authorization: Bearer ${AXONX_TARGET_TOKEN}" \
  --form 'file=@dist/plugins/ACTUAL_FILENAME.whl' \
  http://node-b:1024/upload
```

逐条执行并填写实际返回值：构建返回 wheel 文件名与哈希；上传返回 `answer.location`（目标机绝对路径）和 `answer.path`（目标工作区相对路径）。将 `location` 用于安装：

```bash
axonx plugin install '/ABSOLUTE/LOCATION_FROM_UPLOAD.whl' \
  --target node-b:1024 --client-timeout 600
axonx plugin show axonx-example --target node-b:1024
```

确认安装退出码为 0，核对目标插件版本、`sha256` 和 `content_sha256` 与本地构建结果一致，再用上传返回的 `path` 清理暂存：

```bash
curl --fail-with-body --request DELETE --get \
  --header "Authorization: Bearer ${AXONX_TARGET_TOKEN}" \
  --data-urlencode 'path=tmp/uploads/ACTUAL_UPLOAD_PATH.whl' \
  http://node-b:1024/upload
```

上传默认限额 512 MiB。连接中断时安装可能继续，先确认远端安装结束再重试或清理。依赖插件也须先安装到目标机；目标机已有源码时可直接使用远程 editable 安装：

```bash
axonx plugin install -e /ABSOLUTE/PATH/TO/example --target node-b:1024
```

安装后请求重启，保存返回的 `update_id`，等待恢复并查询该操作至 `succeeded` 或 `failed`，再确认插件和 Task Schema：

```bash
axonx restart_service --target node-b:1024
axonx get_update_status --update-id ACTUAL_UPDATE_ID --target node-b:1024
axonx plugin list --target node-b:1024
axonx get_task_def --task example_add --target node-b:1024
```

本地服务采用相同流程，省略 target。安装/重启响应成功不等于新代码已验证；实际运行前先完成刷新。服务重启会终止它拥有的手动 CLI 执行，不能在研究中途随意重启。

## 4. 运行 Task 并检查证据

先确认 Task Schema、数据覆盖和所需凭据。行情凭据与 AxonX 服务 token 不同；远程执行使用目标机的数据、路径与环境，本机 `export` 不会配置远端服务。

```bash
axonx exec --task demo --task-name check --x 1 --y 2
axonx status --task-id 'base#demo#check' --detail full
axonx read_task_log --task-id 'base#demo#check' --offset -1 --limit 8192
axonx wait_task --task-id 'base#demo#check' --detail full --client-timeout 600
axonx stream_task --task-id 'base#demo#check' --stream true
axonx get_task_context --task-id 'base#demo#check'
axonx get_task_graph --task-id 'base#demo#check'
```

`exec` 同步运行，结束后返回业务输出与 Task 退出码；长任务在另一终端或工具调用中观察。远程执行及全部查询加同一个 `--target`，终端持续显示执行输出。远程断连后执行可能继续，重试前查记录，停止执行使用 `kill`。

```bash
axonx exec --task demo --task-name remote-check --x 1 --y 2 --target node-b:1024
axonx status --task-id 'base#demo#remote-check' --detail full --target node-b:1024
```

参数使用 `--field value`，连字符转下划线、点号生成嵌套对象，值支持布尔、null、数字和 JSON。引用含 `#` 的 ID 与 JSON 数组。`--client-timeout` 默认 60 秒，是客户端连接超时，不是研究业务截止时间。

本地执行设置优先级为 CLI 显式字段 > 服务 `get_config` > 默认值；只有服务连接失败可回退，认证或配置错误会失败。`--workspace-dir`、`--log-dir`、`--timezone`、`--environment.KEY` 等覆盖只影响该命令；服务查询仍观察服务配置的工作区。无服务时直接检查本地 metadata、日志和产物。

### 参考研究链

`qlib_a158` 主链为 ETL → Train → Predict → Backtest，Analysis 从 ETL 独立分支。安装插件并在执行机配置数据凭据后，按顺序运行；每一步确认成功再启动下游，脚本须遇错停止。已有完整原始历史时跳过下载：

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

下载写入共享 `tushare/` 分区，默认回溯 7 天不足以支持多年训练。检查原始历史、滚动特征所需长度和数据权限，缺失行情不能解释为零收益。训练结束日不包含在训练区间，预测不得早于训练结束，预测和选股不能使用未来标签。

也可用一条命令运行完整研究链，由父 Task 管理各阶段：

```bash
axonx exec --task qlib_a158_research --task-name pipeline-01 \
  --etl.start-date 20150101 --etl.end-date 20240131 \
  --train.train-start 20150101 --train.train-end 20230101 \
  --predict.pred-end 20231231 --analysis '{}'
```

结果中的 `stage_task_ids` 指向各阶段，`analysis: {}` 启用分析。复用既有上游时按前面的分阶段命令执行。`qlib_factor` 的可选特征需要显式选择，不能因安装扩展就假定训练已采用新特征。

### 检查运行结果

Task ID 为 `task_type#registration#task_name`，实例名为 1–32 个字母、数字或连字符，省略时自动生成。`started_at` 区分同名多次执行；终态为 `succeeded` 或 `failed`，执行中为 `running`。

| 层次     | 要核验的内容                                                    |
| -------- | --------------------------------------------------------------- |
| 命令     | 退出码、`success`、异常、stdout/stderr 及截断标志               |
| Task     | 实际 ID、`started_at`、终态、输入、步骤和子调用；失败时读取日志 |
| 研究证据 | 实际产物、数据覆盖、业务评估状态、样本数和可比的指标            |

`status`/`wait_task` 默认摘要，`--detail full` 返回完整输入输出；`get_task_context` 提供完整选中记录、路径和输入关系。日志用 `next_offset` 续读，`--started-at TIMESTAMP` 可防止读到同名新执行。列表与图可能有索引刷新延迟，单任务状态直接读取 metadata。

固定名字保存在 `<workspace>/tasks/<task_type>/<task_id>/`；匹配 `YYYYMMDDHH` 加四位字母数字的名字（包括继承名字）保存在 `<workspace>/tmp/tasks/<task_type>/<task_id>/`。两者包含 `metadata.json`、`events.jsonl`、相对 Task 目录的 `log_path`（启用文件日志时为 `task.log`）及 `persistent/runs.jsonl`。执行器为所有 Task 类型统一追加 `started`、`finished` 事件及完整执行元信息，同名重跑保留该日志；执行期间复用 `persistent/task.lock` 文件锁，不创建全局锁目录。从输出 `artifacts` 取实际文件名，将 Task 目录与产物相对路径组合后预览：

```bash
axonx list_entries --path ''
axonx preview_file --path 'tasks/base/base#demo#check/metadata.json' --max-bytes 8192
```

`preview_file` 使用工作区相对路径，CLI 默认 20 行、8192 字节。检查解析错误与截断标记，表格按 `offset`/`limit` 翻页，日志按 `next_offset` 续读。查询通常返回 `{answer, success, metadata}`，`success` 只说明查询完成，还需检查 `answer` 中的 Task 状态和研究结果。

忘记实例名或查找已有实验时，先列出记录：

```bash
axonx list_task_ids
axonx list_task_statuses --task-type backtest --state succeeded
axonx list_task_directories --path tasks/backtest
```

## 5. 比较结果与迭代

先定位问题，再返回相应步骤：

| 情况                                 | 处理                                         |
| ------------------------------------ | -------------------------------------------- |
| 连接、凭据或数据问题                 | 修正环境或补齐数据，核验已有运行后再试       |
| 插件/Task 不存在、版本或 Schema 不符 | 检查执行机的安装、依赖与服务刷新             |
| 代码异常、输入或产物协议错误         | 保留失败证据，修复代码、验证、重新部署运行   |
| 有效结果不支持假设                   | 记录负面结果；有明确新假设且在预算内时再迭代 |

基线、候选和修复后运行使用不同实例名，保留代码/数据版本、参数和失败记录。同名重跑会替换当前目录并保留 `persistent/`。特征变化通常重跑 ETL 及下游，模型变化可复用兼容 ETL，组合规则变化可复用兼容预测；先核验上游修订、特征和协议。

比较时对齐有效日期、样本、股池、成本和指标定义，区分信号质量与组合收益。用于筛选方案的窗口不能同时作为独立确认；确认后继续调参需重新建立确认设计。不必为了得到正收益或更高指标无限尝试。

交付时简要报告：**问题与改动、验证结果、执行目标/工作区、源码或插件版本、Task ID 与 `started_at`、输入修订、关键产物、基线对比与结论**。说明数据质量、交易假设、独立确认情况，以及实际错误和未验证部分。完成标准是有证据地回答研究问题，或明确证据不足及继续所需条件。

## 6. 停止、清理与重跑

需要中止研究时，停止实际执行后再确认状态；取消日志观察不会停止 Task：

```bash
axonx kill --task-id 'base#demo#check' --timeout 5 --force false
axonx status --task-id 'base#demo#check' --detail full
```

`kill` 核验进程身份，子任务会解析到根进程所有者。确认任务已停止且不再需要证据后，才清理目录；不再需要示例插件时可卸载：

```bash
axonx delete_entries --paths '["tasks/base/base#demo#check"]'
axonx plugin uninstall axonx-example
```

删除目录会移除 `persistent/`，没有活动任务保护；卸载插件保留历史产物，常驻服务需重启刷新。启动、重跑和删除同一目录须串行协调。需要保留结果时，改用新实例名运行。

## 7. 其他运行操作（按需）

### 服务更新

修改配置或插件后使用前面的 `restart_service`。需要更新 AxonX 框架时，根据安装来源选择一种方式：

```bash
axonx update_from_git
```

或更新包索引中的发布版本：

```bash
axonx update_from_pip
```

这些操作需要认证和 Daemon 支持；保存返回的 `update_id`，用 `axonx get_update_status --update-id ACTUAL_UPDATE_ID` 查询至完成。失败可能留下部分源码/依赖变更。插件实验使用 `plugin install`，无需每次更新框架。

### 定时运行

将以下内容保存为 `scheduled.yaml`，再启动服务：

```yaml
extends: default
timezone: Asia/Shanghai
cron:
  - expression: "0 16 * * 1-5"
    command: "axonx exec --task download_tushare_task --days-back 7"
```

```bash
axonx app --config scheduled.yaml
```

计划接受五字段表达式和本地 `axonx exec --task NAME`，不支持 shell 管道、重定向或远程选项，不补跑错过时点。配置修改后重启；已启动的定时执行可跨服务重启继续，手动执行随服务停止。检查 Task 状态与 `logs/cron/entry-N.log`，避免固定实例名的计划重叠。

### 展示同步

需要跨机器查看研究结果时，查询目标展示快照；已有合法展示归档时，按前面的上传方法上传，再用返回的相对路径应用：

```bash
axonx task_sync_index --target node-b:1024
axonx sync_tasks --path 'tmp/uploads/ACTUAL_SYNC_ARCHIVE.tar.gz' --target node-b:1024
```

应用后会清理暂存归档。已配置同步组件及对应命令时，也可用 `axonx sync_flush` 从源端发起同步，默认未启用。展示副本可能省略或采样文件，不能执行或作为研究输入；完整备份须保留工作区、外部日志、配置、源码和依赖版本。

### 使用内置 Agent

使用外部 Agent 开发时，直接使用宿主的代码工具与上述命令即可。需要 AxonX 内置 Agent 时，服务机配置 `CLAUDE_CODE_API_KEY`、`CLAUDE_CODE_BASE_URL`、`CLAUDE_CODE_MODEL_NAME`，源码开发将 `components.agent.default.cwd` 设为源码目录，再发起对话：

```bash
axonx agent_chat --message 'Inspect existing research tasks and report their actual status.' --stream true --client-timeout 600
axonx list_agent_sessions --limit 20
```

保存返回的 `metadata.session_id`，将下面的 `<SESSION_ID>` 换成实际值，按需继续对话、读取历史或管理会话：

```bash
axonx agent_chat --session-id '<SESSION_ID>' --message 'Read the logs for the task we just discussed.' --stream true --client-timeout 600
axonx get_agent_session --session-id '<SESSION_ID>' --limit 20
axonx rename_agent_session --session-id '<SESSION_ID>' --title 'Factor validation'
axonx tag_agent_session --session-id '<SESSION_ID>' --tag research
axonx fork_agent_session --session-id '<SESSION_ID>' --title 'Alternative approach'
axonx cancel_agent_turn --session-id '<SESSION_ID>'
axonx delete_agent_session --session-id '<SESSION_ID>'
```

取消轮次与 Task kill 分开处理；运行中的会话不能删除。命令默认返回一次查询结果，需要实时事件时使用 `--stream true`，供程序读取时再加 `--stream-format json`。`--target`、`--token`、`--client-timeout`、`--stream`、`--stream-format` 控制连接和显示，不是研究 Task 参数。
