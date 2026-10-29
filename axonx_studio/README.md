# AxonX Studio

English · [简体中文](https://github.com/FlowLLM-AI/AxonX/blob/main/axonx_studio/README_ZH.md)

AxonX Studio is the browser workspace for [AxonX](https://github.com/FlowLLM-AI/AxonX). Run Tasks, develop with an Agent, and inspect logs, dependencies, workspace files and research charts. It supports English/Chinese, light/dark themes, and backend-configured remote machines.

![Studio home in the simulated Playground](https://raw.githubusercontent.com/FlowLLM-AI/AxonX/main/docs/figures/studio/home.png)

The screenshot uses the static Playground with simulated data and execution.

## Install and start

Use Python 3.12+ on macOS or Linux. Prebuilt Studio packages require no Node.js.

```bash
pip install "axonx[studio]"
export AXONX_SERVICE_TOKEN='replace-with-your-service-token'
axonx app --service.host 127.0.0.1
```

Open <http://127.0.0.1:1024/> and enter the token in **Settings → Local service token**. Studio stores it in browser local storage. If AxonX is already installed, `pip install axonx-studio` and restart the service; `service.web_enabled` must be enabled.

Select **Task definitions → demo**, enter `x = 2`, `y = 3`, and run. Inspect the result and logs in Task details. Navigation preserves the command connection; reloading or closing the browser can stop execution. Leave Task Name empty for independent runs; a fixed-name rerun replaces the finished run.

Open **Research → Data processing** for datasets produced by ETL Tasks, **Daily operations → Prediction comparison** to check online and offline predictions, and **Research → Strategy comparison** to compare offline backtest results.

Follow [Using Studio](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/en/getting-started/studio.md) for navigation and failures, [research setup](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/en/research/workflow.md) for plugins/data, and [Agent configuration](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/en/agent/configuration.md) for model credentials and code tools. Ordinary Tasks need no model credentials.

## Static hosting

```bash
npm install @flowllm-ai/axonx-studio
```

Serve `node_modules/@flowllm-ai/axonx-studio/dist/`. Proxy `/health`, `/jobs`, `/upload`, `/mcp` and `/proxy` on the same origin to an AxonX backend, preserving Authorization and SSE streaming. Hash routes need no server-side page routes. Python hosting uses the packaged `dist/` through `static_dir()`.

## Develop from source

Use Node.js 22.13+ (22.x), 24.x or 26+. Start the backend using the [contribution guide](https://github.com/FlowLLM-AI/AxonX/blob/main/CONTRIBUTING.md), then run:

```bash
cd axonx_studio
npm ci
npm run dev
```

Open <http://localhost:4173/>. The development proxy defaults to `http://127.0.0.1:1024`; set `AXONX_DEV_SERVER` and restart Vite to change it. Vite also reads the repository-root `.env`. This variable configures only the development proxy.

```bash
# From the repository root:
npm --prefix axonx_studio run build
pip install ./axonx_studio
```

Restart AxonX after installation. Python distributions include existing `dist/`; `npm pack`/`npm publish` run the build through `prepack`. `npm run preview` previews static assets without the development API proxy.

[Extending Studio](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/en/development/studio.md) owns the directory map, routing, API/forms, generated contracts, Playground and checks. [Artifact contracts](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/en/reference/research-artifacts.md) define research views; [deployment](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/en/guides/deployment.md) covers remote targets and hosting.

Released under the [Apache License 2.0](https://github.com/FlowLLM-AI/AxonX/blob/main/axonx_studio/LICENSE).
