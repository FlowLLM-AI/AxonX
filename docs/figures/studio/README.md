# Studio screenshots

These 14 PNGs show the complete English AxonX Studio 0.3.0 application, including its header, navigation, and Playground notice. They are browser screenshots, without crops or stitched panels. English and Chinese documentation share the same images.

The source is the repository's static Playground with its built-in synthetic Tasks and artifacts. Securities, scores, returns, and curves are fictional. No model request, real research execution, or external notification was sent.

Start the source UI from the repository root:

```bash
DOCS_BASE=/ npm --prefix axonx_studio run dev:playground -- --host 127.0.0.1 --port 4173
```

Open `http://127.0.0.1:4173/playground/?lang=en`, use a light appearance, and capture at a **1728 CSS-pixel width with device scale factor 2**. PNG width is **3456 pixels**. Adjust viewport height to include each report's bottom edge; tables and code panels retain their normal scrolling behavior. Wait for fonts, artifacts, and chart animations before capturing. Preserve the Playground notice and exclude private browser state.

Routes below are relative to `#local/`. URL-encode Task IDs and file paths when constructing links.

| File                      | Route                                                  | Selection                                                                     | PNG size    |
| ------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------------------- | ----------- |
| `home.png`                | `home/overview`                                        | Home                                                                          | 3456 × 2512 |
| `agent-new-chat.png`      | `agent/new`                                            | Empty composer; no message sent                                               | 3456 × 2560 |
| `task-list.png`           | `runtime/tasks`                                        | Grouped Task list                                                             | 3456 × 2560 |
| `task-lineage.png`        | `runtime/task/backtest#playground_backtest#demo`       | Dependencies                                                                  | 3456 × 2200 |
| `task-definitions.png`    | `task-defs/catalog/playground_train`                   | Expand the Playground group                                                   | 3456 × 2560 |
| `workspace-preview.png`   | `workspace/files/tushare/README.md`                    | Markdown preview                                                              | 3456 × 2560 |
| `api-catalog.png`         | `apis/catalog/get_task_def`                            | Call with `task=playground_train`                                             | 3456 × 2320 |
| `etl-results.png`         | `etl/runs/etl#playground_etl#demo`                     | Complete report                                                               | 3456 × 2560 |
| `factor-results.png`      | `factors/runs/analysis#playground_analysis#demo`       | Complete report                                                               | 3456 × 2560 |
| `training-results.png`    | `train/runs/train#playground_train#demo`               | Summary, parameters, curves, and artifacts                                    | 3456 × 2560 |
| `prediction-results.png`  | `predict/runs/predict#playground_predict#demo`         | Complete report                                                               | 3456 × 2884 |
| `backtest-overall.png`    | `backtest/runs/backtest#playground_backtest#demo`      | Overall                                                                       | 3456 × 2320 |
| `backtest-net-return.png` | `backtest/runs/backtest#playground_backtest#demo`      | Net return                                                                    | 3456 × 3520 |
| `strategy-overview.png`   | `compare/strategies/backtest#playground_backtest#demo` | Select `volatile` as B; Overview; expand chart zoom to the full shared window | 3456 × 2720 |

Training summary and curves share one screenshot. Strategy selection, metrics, and returns share one screenshot. The download and notification guides link to the common task-definition interface. Keep image references and `github-pages/site/theme/home.ts` dimensions synchronized when replacing a screenshot.
