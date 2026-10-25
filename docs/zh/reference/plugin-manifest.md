# 插件包与贡献协议

插件是通过 `axonx.plugins` 入口点发布的 Python 包，打包的 `plugin.yaml` 只声明 Tasks。发现、安装、执行各自独立。

![插件发现与贡献](../../figures/reference/plugin.svg)

## 三种名称

| 名称               | 示例          | 使用位置                              |
| ------------------ | ------------- | ------------------------------------- |
| distribution       | axonx-example | pip 元数据、安装与卸载                |
| plugin entry point | example       | 插件发现与 manifest 所属包            |
| Task 注册名        | example_task  | exec --task、get_task_definition.task |

这些名字不要求相同。Task ID 另由任务类型、注册名与实例名称组成，不能用 distribution 代替注册名执行任务。

## 最小包布局

```text
example-project/
  pyproject.toml
  axonx_example/
    __init__.py
    plugin.yaml
    tasks.py
```

pyproject.toml：

```toml
[build-system]
requires = ["setuptools>=84.0.0"]
build-backend = "setuptools.build_meta"

[project]
name = "axonx-example"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["axonx>=0.1.0"]

[project.entry-points."axonx.plugins"]
example = "axonx_example"

[tool.setuptools.packages.find]
where = ["."]
include = ["axonx_example*"]

[tool.setuptools.package-data]
axonx_example = ["plugin.yaml"]
```

entry point 指向一个 Python package；plugin.yaml 必须被包含进 wheel。只写源码 manifest 而未包含 package-data，会导致安装后发现失败。

## manifest 字段

```yaml
tasks:
  example_task: axonx_example.tasks:ExampleTask
components: {}
jobs: {}
```

| 字段  | 类型                      | 默认值 | 契约                     |
| ----- | ------------------------- | ------ | ------------------------ |
| tasks | dict[非空名,非空符号目标] | {}     | 符号必须为 BaseTask 子类 |

顶层禁止额外字段；根必须是 YAML mapping。名称与字符串目标去掉首尾空白并要求非空。`module:Class` 目标先导入模块，再逐级取属性；字符串不满足格式、属性不存在或不是目标基类均失败。 Task 可以从同一 wheel 内额外的包或独立模块导入辅助代码；通过服务安装时，这些模块会与入口包一起刷新。

Task 必须声明固定 TaskType、input_cls 和 output_cls，建议添加详细的类 docstring。查询定义时从类 docstring 提取 description；缺少或仅含空白时返回空字符串。Task 最小开发流程见 [已有开发指南](../dev_guide.md)。

所有注册的 Task 都必须遵守 [`BaseTask`](../../../axonx/task/core/task.py) 的公共开发协议。
[`axonx.task.contracts`](../../../axonx/task/contracts/) 中的研究基类是可选标准契约；采用后必须保留其参数字段与校验规则。
核心协议与标准研究契约的适用范围及实现要求见[必须遵守的开发协议](../dev_guide.md#必须遵守的开发协议)。

## 扩展边界

`plugin.yaml` 只允许 `tasks: {注册名: module:Class}`。`components` 和 `jobs` 已移除，应用启动也不再读取 `plugins.sources`。安装通过 Plugin CLI 显式完成，新的 exec/定义查询子进程会加载安装环境；App 本身不加载研究插件。

服务组件与 Job 使用 `Application(providers=...)` 和应用配置。不同插件或内置 Task 的同名注册仍会报错，不自动覆盖。

## wheel 与内容指纹

| 字段           | 含义                     | 用途               |
| -------------- | ------------------------ | ------------------ |
| sha256         | wheel 文件字节的 SHA-256 | 安装制品校验       |
| content_sha256 | 插件内容指纹             | 构建缓存与内容身份 |
| requirements   | wheel 的依赖元数据       | 安装环境需求       |

相同源内容与缓存不代表 wheel 字节必然相同；不要拿 content_sha256 替代本地构建 wheel 的 SHA256。远程 install 必须接收 POST /upload 返回的 path 与该本地 wheel 的 SHA256。editable 只适用于本地源码环境，不能远程部署。

```bash
axonx plugin inspect ./plugins/example
axonx plugin build ./plugins/example --output ./dist
axonx plugin install ./plugins/example
axonx plugin list
```

这些命令使用选定环境中的路径执行检查、构建或安装。安装不刷新服务已加载对象；需要重新加载 schema 或贡献时重启服务。详见[插件管理](../plugins/management.md#校验和与服务状态)。

## 命名配置贡献

同一个包还可以发布 axonx.configs entry point：

```toml
[project.entry-points."axonx.configs"]
example = "axonx_example.config:example"

[tool.setuptools.package-data]
axonx_example = ["plugin.yaml", "config/*.yaml"]
```

如果 attr 是已存在对象，resolver 加载它，若可调用则调用并取得 YAML/JSON 路径；否则把目标包作为目录，按 attr/name 取对应配置文件。必须定位到一个实际配置文件。同名配置歧义会拒绝，不静默选一个。

仓库 qlib_a158 使用独立 distribution axonx-qlib-a158、插件 entry-point qlib_a158 与 axonx_qlib_a158 包，可作为真实包结构参考。

## 相关文档

- [插件管理](../plugins/management.md)
- [插件 API](../api/plugins-sync.md)
- [CLI 参考](cli.md)

实现依据：`axonx/plugin/manifest.py`、`loading.py`、`contributions.py`、`wheel.py`、`config/resolver.py`。
