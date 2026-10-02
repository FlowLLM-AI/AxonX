# AxonX Studio

AxonX 的任务与量化研究工作台，提供任务提交、运行状态、日志和研究结果视图。

## 安装

```bash
pip install "axonx[studio]"
export AXONX_SERVICE_TOKEN='replace-with-your-local-service-token'
axonx start --service.host 127.0.0.1
```

打开 <http://127.0.0.1:1024/>，在 **Settings → Service token** 中填入相同 token。已有 AxonX 环境也可单独安装 `axonx-studio`。发布包包含静态资源，无需 Node.js 或本地构建。

npm 包分发相同的静态资源：

```bash
npm install @flowllm-ai/axonx-studio
```

资源位于 `node_modules/@flowllm-ai/axonx-studio/dist/`。此包用于独立静态托管，后端服务仍由 AxonX 提供；静态站点需将 API 请求代理到后端。使用 AxonX 内置托管时，安装上面的 Python 包即可。

## 源码开发

先从仓库根目录安装核心与开发依赖，再构建 Studio：

```bash
pip install -e '.[dev]'
cd axonx_studio
npm ci
npm run build
cd ..
pip install ./axonx_studio
```

开发服务器、目录结构和验证命令见 [Studio 开发](https://flowllm-ai.github.io/AxonX/zh/development/studio)，连接与操作见 [Studio 入门](https://flowllm-ai.github.io/AxonX/zh/getting-started/studio)。
