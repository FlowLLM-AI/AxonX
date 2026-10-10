# 插件安装与部署

插件是提供 AxonX Task、Component 和 Job 的 Python 包。本地管理命令操作当前 Python 环境，只有显式 `--target` 才操作远程服务。构建与安装会读取插件代码和依赖。通过服务更新仅贡献 Task 的 wheel 无需重启；Component/Job 和依赖变更需检查 `restart_required`。

![插件部署流程](../../figures/guides/plugin-deployment.svg)

## 三种名称

| 名称         | 用途                     | 来源                           |
| ------------ | ------------------------ | ------------------------------ |
| distribution | Python 包安装与卸载      | pyproject.toml 的 project.name |
| plugin name  | 发现与区分插件入口       | axonx.plugins entry point      |
| Task 注册名  | submit / exec / 定义查询 | plugin.yaml 的 tasks           |

这三个名字可能不同。不要把 distribution 名直接传给 `--task`，先查看插件贡献中的 Task 注册名。

## 查看当前环境

```bash
axonx plugin list
axonx plugin show '<distribution 或插件名>'
axonx plugin inspect '<distribution 或插件名>'
```

查看字段包括 distribution、version、入口名、requirements 和贡献。Task 注册名仍需进一步用定义接口获取输入输出 Schema。

本地 CLI 直接检查当前环境，不经 HTTP。服务使用另一虚拟环境时，CLI 本地结果不一定代表常驻服务环境。

## 准备插件源码

研究插件尚未发布到 PyPI。先安装 AxonX 主包，克隆仓库，再从仓库根目录执行本页命令：

```bash
pip install axonx
git clone https://github.com/FlowLLM-AI/AxonX.git
cd AxonX
```

Alpha158 是基础插件；factor 依赖 Alpha158，strategy 依赖 factor。使用下游插件前，必须在同一执行环境按 Alpha158 → factor → strategy 顺序安装满足版本要求的上游插件。安装器通过 pip 解析依赖，不会自动定位仓库中的其他插件目录；上游未安装或版本不满足要求时，会尝试从包索引查找。

## 从源码构建和检查

仓库中的 qlib_a158 目录可作为源码路径示例：

```bash
axonx plugin inspect ./plugins/qlib_a158
axonx plugin build ./plugins/qlib_a158 --output ./dist/plugins
```

源码构建需要 pyproject、manifest 和有效贡献，工具会构建 wheel 并检查内容。构建不是运行研究任务，也不需要提交 Task。

没有 `--output` 时，CLI 默认缓存位于当前目录的 `.axonx/plugins/artifacts/<content_sha256>`。这个缓存路径由插件 CLI 自己选择，不自动跟随另一个服务的 workspace_dir。

源码哈希直接跳过 `node_modules`、`.axonx`、Python 环境和工具缓存，以及根目录构建产物，不遍历其内容。上述被忽略的文件和目录不会改变构建缓存键。名为 `build` 或 `dist` 的嵌套源码包仍参与哈希；未忽略源码中的软链接仍会报错。这些规则独立于 `.gitignore`。

对已有 wheel 可直接 inspect/install，但不能同时指定 `--output`：

```bash
axonx plugin inspect './dist/plugins/<实际 wheel 文件名>.whl'
```

## 本地安装

```bash
# 本机 Agent / 插件开发：按依赖顺序安装到当前环境
axonx plugin install -e ./plugins/qlib_a158
# 按需安装因子和策略扩展
axonx plugin install -e ./plugins/qlib_factor
axonx plugin install -e ./plugins/qlib_strategy
```

editable 只能用于本地源码目录，不支持 `--target` 或 `--output`。执行服务必须使用当前 Python 环境。修改 Python 源码后无需重新安装，但需重启常驻服务以重新加载 Task、Job 和 Component；依赖、入口点等安装元数据变化后需重新安装。editable 安装仍会先构建并检查 wheel。

固定版本实验或部署使用普通安装，从源码构建并安装 wheel；源码变化后需重新安装，并重启已运行的本机服务：

```bash
axonx plugin install ./plugins/qlib_a158
```

服务配置的 `plugins.sources` 可在启动时安装来源，路径解析见[配置参考](../reference/configuration.md)。已安装且有效的插件通过入口点发现，不使用一个照搬其他项目的显式启用列表。

## 部署到远程

```bash
export AXONX_TARGET_TOKEN='<远程服务 token>'
axonx plugin list --target 'http://research.example:1024'
axonx plugin install ./plugins/qlib_a158 --target 'http://research.example:1024'
# 按需安装，保持相同 target 和依赖顺序
axonx plugin install ./plugins/qlib_factor --target 'http://research.example:1024'
axonx plugin install ./plugins/qlib_strategy --target 'http://research.example:1024'
```

CLI 在本机把源码构建为 wheel，上传到远程 `/files`，核对返回 sha256，再调用远程 install_plugin，并在结束后清理暂存文件。安装 Job 在目标服务的 Python 环境运行。手动通过 HTTP 或 MCP 安装时，先用二进制或 multipart `POST /files` 上传 wheel，再将返回的 path 与 sha256 传给同一服务的 `install_plugin`；见[文件上传与清理](../api/workspace.md#文件上传与清理)。

`plugin build` 只在本机执行，不支持 `--target`。远程 inspect 用于查询目标已安装插件，而不是把本机源码目录传到目标后检查。

## 校验和与重启

| 字段             | 解释                                              |
| ---------------- | ------------------------------------------------- |
| content_sha256   | 内容/源码指纹，用于构建缓存和内容识别             |
| sha256           | 具体 wheel 文件的校验和，用于传输与安装核验       |
| restart_required | 运行中的 Component/Job 或被替换的依赖是否要求重启 |

两个 sha256 字段并不保证相同：wheel 的压缩与包内容封装会改变具体文件字节。安装接口应传上传回执的 wheel sha256，不传源码指纹。

通过 `install_plugin` 安装或更新仅贡献 Task 的 wheel，会刷新运行中服务的插件包导入。后续定义查询和提交使用更新后的 Task 类、参数模型与辅助模块，包括同一 wheel 内额外的包或独立模块，无需重启。卸载仅贡献 Task 的插件后，后续查询和提交不再包含其注册信息。相同 wheel 跳过安装，并保留缓存中的类。

安装、卸载会与 Task 查询和提交协调，保护范围持续到 worker 启动；同一进程的所有 Application（包括使用不同事件循环的实例）共享此协调，等待时不阻塞服务事件循环。取消安装/卸载请求或关闭其 Application 时，会等待已开始的环境变更结束，再释放协调并清理暂存文件。取消不会回滚 pip 的变更，之后应核对实际安装的插件。插件包之间的导入引用一起刷新，AxonX 与第三方依赖模块保持原有身份。覆盖文件时，不迁移运行中的 Task，也不固定其代码版本。

当前或被移除的 Component/Job 贡献仍要求 `restart_required=true`；安装替换已有依赖版本时也要求重启。待处理的重启提示持续到服务进程重启，重复安装相同 wheel 或移除 Component/Job 贡献都不会清除该提示。直接 `pip install` 或在安装 Job 之外修改源码不会触发此刷新，变更后应重启服务。editable 安装也可能需要解释器启动才能加载导入钩子。

安装后仅在 `restart_required=true` 时重启，再验证：

```bash
axonx list_installed_task_definitions --target 'http://research.example:1024'
axonx get_task_definition --task '<插件 Task 注册名>' \
  --target 'http://research.example:1024'
```

## 卸载与排障

```bash
axonx plugin uninstall '<distribution 或插件名>'
axonx plugin uninstall '<distribution 或插件名>' \
  --target 'http://research.example:1024'
```

卸载影响后续加载代码，不自动删除历史研究产物。已有 metadata 仍可读，但重跑可能需要恢复原插件版本。

| 问题                 | 检查                                  |
| -------------------- | ------------------------------------- |
| 注册名冲突           | 插件贡献是否与内置或其他插件同名      |
| manifest 无效        | 类型、module:Class 与类基类           |
| 安装成功但 UI 没更新 | restart_required、目标机器、运行环境  |
| wheel 校验失败       | 使用上传回执 sha256，重新传输正确文件 |
| 缺模型依赖           | 检查 requirements 与目标环境的设备库  |

[插件 manifest](../reference/plugin-manifest.md) · [远程机器](../guides/remote-machines.md) · [已有开发指南](../dev_guide.md)

源码：[插件 CLI](../../../axonx/plugin_kit/cli.py)、[wheel 构建](../../../axonx/plugin_kit/wheel.py)、[安装器](../../../axonx/plugin_kit/installer.py)。

## 研究插件

[Alpha158](../../../plugins/qlib_a158/README_ZH.md) · [Qlib Factor](../../../plugins/qlib_factor/README_ZH.md) · [Qlib Strategy](../../../plugins/qlib_strategy/README_ZH.md)
