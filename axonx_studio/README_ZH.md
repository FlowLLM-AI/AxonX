# AxonX Studio

[English](https://github.com/FlowLLM-AI/AxonX/blob/main/axonx_studio/README.md) · 简体中文

AxonX Studio 是 [AxonX](https://github.com/FlowLLM-AI/AxonX) 的浏览器工作区，用于执行 Task、通过 Agent 开发、检查日志、依赖、工作区文件与研究图表。支持中英文、明暗主题和后端配置的远程机器。

![模拟 Playground 中的 Studio 首页](https://raw.githubusercontent.com/FlowLLM-AI/AxonX/main/docs/figures/studio/home.png)

截图来自静态 Playground，数据与执行均为模拟。

## 安装与启动

使用 macOS/Linux 和 Python 3.12+。预构建 Studio 包不需要 Node.js。

```bash
pip install "axonx[studio]"
export AXONX_SERVICE_TOKEN='replace-with-your-service-token'
axonx app --service.host 127.0.0.1
```

打开 <http://127.0.0.1:1024/>，在**设置 → 本机服务 token** 填入相同 token。Studio 将其保存在浏览器 local storage。已安装 AxonX 时可执行 `pip install axonx-studio` 后重启服务，并确保 `service.web_enabled` 已开启。

进入**任务定义 → demo**，填写 `x = 2`、`y = 3` 后运行，在任务详情检查结果和日志。页面切换保留命令连接，刷新或关闭浏览器可能停止执行。独立实验将 Task Name 留空；固定名称重跑会替换已结束记录。

导航和故障处理见 [Studio 使用](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/getting-started/studio.md)，插件/数据见[研究准备](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/research/workflow.md)，模型凭据和代码工具见 [Agent 配置](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/agent/configuration.md)。普通 Task 不需要模型凭据。

## 静态托管

```bash
npm install @flowllm-ai/axonx-studio
```

托管 `node_modules/@flowllm-ai/axonx-studio/dist/`，将同源 `/health`、`/jobs`、`/upload`、`/mcp` 和 `/proxy` 代理到 AxonX 后端，保留 Authorization 与 SSE 流。Hash 路由无需服务端页面路由。Python 托管通过包的 `static_dir()` 加载 `dist/`。

## 源码开发

使用 Node.js 22.13+ (22.x)、24.x 或 26+。按[贡献指南](https://github.com/FlowLLM-AI/AxonX/blob/main/CONTRIBUTING_ZH.md)启动后端，再运行：

```bash
cd axonx_studio
npm ci
npm run dev
```

打开 <http://localhost:4173/>。开发代理默认连接 `http://127.0.0.1:1024`，修改 `AXONX_DEV_SERVER` 后重启 Vite。Vite 也读取仓库根目录的 `.env`。该变量只配置开发代理。

```bash
# 从仓库根目录运行：
npm --prefix axonx_studio run build
pip install ./axonx_studio
```

安装后重启 AxonX。Python 分发包含现有 `dist/`；`npm pack`/`npm publish` 通过 `prepack` 自动构建。`npm run preview` 仅预览静态资源，不提供开发 API 代理。

[扩展 Studio](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/development/studio.md)统一维护目录职责、路由、API/表单、生成契约、Playground 和检查。[产物契约](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/reference/research-artifacts.md)定义研究视图，[部署指南](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/guides/deployment.md)说明远程目标与托管。

使用 [Apache License 2.0](https://github.com/FlowLLM-AI/AxonX/blob/main/axonx_studio/LICENSE) 许可证。
