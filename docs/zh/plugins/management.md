# 插件安装与部署

插件是通过 `axonx.plugins` 入口点和 `plugin.yaml` 注册 Task 的 Python distribution。管理命令修改其实际执行的 Python 环境。

![插件包身份与显式远程 wheel 部署](../../figures/plugins/distribution.svg)

## 三种名称

| 名称         | 用途                                         |
| ------------ | -------------------------------------------- |
| distribution | pip 安装和卸载，来自 `project.name`          |
| 插件入口名   | 标识指向包的 `axonx.plugins` 入口            |
| Task 注册名  | `plugin.yaml.tasks` 的键，用于 `exec --task` |

执行前查询实际注册名。包名不能代替 Task 名。

## 查看当前环境

```bash
axonx plugin list
axonx plugin show DISTRIBUTION
axonx plugin inspect DISTRIBUTION
```

本地命令检查当前解释器。添加 `--target HOST:PORT` 则在服务解释器中执行。每次命令启动新进程并发现已安装元数据。

## 准备插件源码

研究插件尚未发布到 PyPI。克隆本仓库，并按 Alpha158 → factor → strategy 顺序安装。pip 解析依赖，但不会自动定位相邻源码目录；研究依赖未满足时可能访问配置的包索引。

## 从源码构建和检查

```bash
axonx plugin build ./plugins/qlib_a158 --output ./dist/plugins
axonx plugin inspect './dist/plugins/ACTUAL_FILENAME.whl'
```

构建输出包含 `wheel`、`sha256`、`content_sha256`、distribution、version、requirements 和注册信息。记录实际 wheel 文件名。不传 `--output` 时，缓存位于 CLI 工作目录的 `.axonx/plugins/artifacts/<源码指纹>`。已有 wheel 不能与 `--output` 同用。源码指纹忽略环境和缓存，拒绝参与哈希的源码软链接。

## 本地安装

```bash
axonx plugin install -e ./plugins/qlib_a158
axonx plugin install -e ./plugins/qlib_factor
axonx plugin install -e ./plugins/qlib_strategy
```

editable 仍会先构建并校验 wheel，要求源码目录，不能传 `--output`。普通 `plugin install PATH` 安装构建或指定的 wheel。安装器先安装除 AxonX 自身外的声明依赖，再以不解析依赖的方式强制重装插件，并核验安装后的来源和内容。应自行确认当前 AxonX 版本满足插件要求。

## 部署到远程

指定 target 只转发命令，不传输本地文件。`plugin install ./source --target HOST:PORT` 会在目标服务工作区解释 `./source`。从本地源码部署时，应完整执行：

1. 本地构建 wheel。
2. 将 wheel 上传到目标服务的 `POST /upload`。
3. 通过同一服务的 `cli` Job 安装返回的绝对 `location`。
4. 使用返回的工作区相对 `path` 清理暂存文件。
5. 重启常驻服务，刷新 Task 目录并验证定义。

以下脚本在本地构建 wheel 后运行，需替换文件名、目标地址和 token；脚本检查安装结果，并在成功或失败后清理上传文件：

```python
import asyncio
import hashlib
import json
import os
from pathlib import Path
from axonx.client.http import HttpClient

async def deploy():
    wheel = Path("dist/plugins/ACTUAL_FILENAME.whl")
    expected_sha256 = hashlib.sha256(wheel.read_bytes()).hexdigest()
    async with HttpClient(
        target="http://research.example:1024",
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
            if installed["sha256"] != expected_sha256:
                raise RuntimeError("Installed wheel differs from local wheel")
            print(installed)
        finally:
            await client.discard_file(uploaded.path)

asyncio.run(deploy())
```

这里显式比较本地哈希与安装结果，在安装后确认 wheel 一致。CLI 不接受调用方传入预期哈希。安装器另行核验已安装来源与目标机所读 wheel 的一致性。清理不会回滚安装。安装请求被中断或超时后，应检查目标环境再决定是否重试，pip 可能已经修改文件。

使用 curl 时，通过 `/upload` 的 `-F 'file=@LOCAL.whl'` 上传，再执行 `axonx plugin install '<answer.location>' --target HOST:PORT --client-timeout 600`，最后用 `DELETE /upload?path=<answer.path>` 清理。CLI 认证读取 `AXONX_TARGET_TOKEN`。上传、安装、清理和验证必须使用同一服务。

`location` 是供目标机安装使用的绝对路径；`path` 是供上传清理使用的远程工作区相对路径。本地源码路径不能替代它们。目标机已存在 wheel 或源码目录时可直接安装；远程 editable 也只引用目标机已有源码。

## 校验和与重启

`sha256` 标识 wheel 字节，`content_sha256` 标识规范化插件内容，两者不同。安装结果不提供重启标志，也不刷新常驻服务已加载模块。新的 `exec`、`plugin` 进程重新发现插件，常驻定义查询和 Studio 使用启动时目录和已缓存类。注册、参数模型或已加载依赖变化后应重启服务：

```bash
axonx restart_service --target research.example:1024
# 等待服务恢复后：
axonx plugin list --target research.example:1024
axonx list_task_defs --target research.example:1024
axonx get_task_def --task qlib_a158_etl --target research.example:1024
```

重启响应成功只代表已接受操作，完成情况见 `get_update_status`。插件环境变更没有串行协调，已有进程也不固定代码版本，应自行协调并发安装。

## 卸载与排障

```bash
axonx plugin uninstall DISTRIBUTION --target research.example:1024
```

卸载删除已安装代码，不删除历史产物。重启常驻服务以刷新目录。排障时区分本地文件路径、远程 `location`、远程 `path`、目标解释器、依赖是否满足和 Task 注册名，并检查错误及退出码。

[插件 manifest](../reference/plugin-manifest.md) · [文件上传与清理](../api/workspace.md) · [开发指南](../dev_guide.md)

源码：[CLI](../../../axonx/cli/commands.py)、[安装器](../../../axonx/plugin/installer.py)、[HTTP 客户端](../../../axonx/client/http.py)。

## 研究插件

[Alpha158](../../../plugins/qlib_a158/README_ZH.md) · [Qlib Factor](../../../plugins/qlib_factor/README_ZH.md) · [Qlib Strategy](../../../plugins/qlib_strategy/README_ZH.md)
