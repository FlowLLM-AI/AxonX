# 插件安装与部署

插件是提供 AxonX Task、Component 和 Job 的 Python 包。命令操作当前 Python 环境；显式 `--target` 将 CLI 转发到目标服务的子进程。构建与安装会读取插件代码和依赖。

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

editable 需要选定环境中的源码目录，不能与 `--output` 同用；指定 target 时源码路径属于目标机器。执行服务必须使用当前 Python 环境。修改 Python 源码后无需重新安装，但需重启常驻服务以重新加载 Task、Job 和 Component；依赖、入口点等安装元数据变化后需重新安装。editable 安装仍会先构建并检查 wheel。

固定版本实验或部署使用普通安装，从源码构建并安装 wheel；源码变化后需重新安装，并重启已运行的本机服务：

```bash
axonx plugin install ./plugins/qlib_a158
```

服务配置的 `plugins.sources` 可在启动时安装来源，路径解析见[配置参考](../reference/configuration.md)。已安装且有效的插件通过入口点发现，不使用一个照搬其他项目的显式启用列表。

## 部署到远程

远程 CLI 参数中的路径属于目标机器。上传与安装分开执行：

```bash
axonx plugin build ./plugins/qlib_a158 --output ./dist/plugins
curl -s http://research.example:1024/upload \
  -H "Authorization: Bearer $AXONX_TARGET_TOKEN" \
  -F 'file=@./dist/plugins/<实际 wheel 文件名>.whl'
axonx plugin install '<上传返回的 answer.location>' \
  --target research.example:1024 --client-timeout 300
axonx plugin list --target research.example:1024
```

上传返回 workspace 相对路径 `path`、服务端绝对路径 `location` 和 `size`。远程安装使用 `location`。通过 `DELETE /upload?path=<返回的 path>` 显式清理上传文件；`plugin install` 不删除输入文件。上游插件也需先构建 wheel，再按依赖顺序安装。

`plugin build`、`inspect` 和 editable 安装也支持 `--target`，参数路径均属于目标机器。editable 安装不能使用 `--output`。指定 `--target` 不再自动在本机构建或上传。

## 校验和与服务状态

wheel 检查和安装保留内容与 wheel 校验和。安装只修改选定解释器的环境，不刷新常驻服务的模块，也不追踪 `restart_required`。新的 CLI 进程加载已安装环境；服务中已经加载的对象可以保持旧版本，重启后重新加载。已有进程后续导入模块也可能读取新文件，因此不提供版本隔离。

插件操作不协调并发 pip 修改或 Task 启动。安装完成后再执行依赖它的命令。Task 执行、metadata 发布、仓库刷新、删除和副本应用不再获取框架 Task 或工作区锁。metadata 文件仍通过原子替换写入。保留 Run ID、进程归属及已观察生命周期检查，但检查与写入不构成事务。调用方需顺序修改同一 Task 目录；并发同名执行、重置、删除和同步不再协调。

## 卸载与排障

```bash
axonx plugin uninstall '<distribution 或插件名>'
axonx plugin uninstall '<distribution 或插件名>' \
  --target 'http://research.example:1024'
```

卸载影响后续加载代码，不自动删除历史研究产物。已有 metadata 仍可读，但重跑可能需要恢复原插件版本。

| 问题                 | 检查                                       |
| -------------------- | ------------------------------------------ |
| 注册名冲突           | 插件贡献是否与内置或其他插件同名           |
| manifest 无效        | 类型、module:Class 与类基类                |
| 安装成功但 UI 没更新 | 目标机器、服务已加载对象、运行环境         |
| wheel 校验失败       | 使用本地 wheel 的 SHA256，重新传输正确文件 |
| 缺模型依赖           | 检查 requirements 与目标环境的设备库       |

[插件 manifest](../reference/plugin-manifest.md) · [远程机器](../guides/remote-machines.md) · [已有开发指南](../dev_guide.md)

源码：[插件 CLI](../../../axonx/plugin_kit/cli.py)、[wheel 构建](../../../axonx/plugin_kit/wheel.py)、[安装器](../../../axonx/plugin_kit/installer.py)。

## 研究插件

[Alpha158](../../../plugins/qlib_a158/README_ZH.md) · [Qlib Factor](../../../plugins/qlib_factor/README_ZH.md) · [Qlib Strategy](../../../plugins/qlib_strategy/README_ZH.md)
