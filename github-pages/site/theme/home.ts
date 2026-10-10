import signalQuality from "../../figures/benchmark/qlib-signal-quality.svg";
import portfolioResults from "../../figures/benchmark/qlib-topn-results.svg";
import lineage from "../../figures/studio/task-lineage.png";
import training from "../../figures/studio/training-curves.png";
import backtest from "../../figures/studio/backtest-overall.png";
import comparison from "../../figures/studio/strategy-overview.png";

export const stages = [
  {
    id: "question",
    number: "01",
    page: "agent/research-prompt",
    color: "cyan",
  },
  { id: "development", number: "02", page: "dev_guide", color: "violet" },
  { id: "execution", number: "03", page: "research/workflow", color: "blue" },
  { id: "evidence", number: "04", page: "research/results", color: "amber" },
  {
    id: "iteration",
    number: "05",
    page: "research/experiments",
    color: "green",
  },
] as const;

export const baseline = [
  { id: "data", page: "research/tushare" },
  { id: "features", page: "research/workflow" },
  { id: "training", page: "research/results" },
  { id: "prediction", page: "research/results" },
  { id: "backtest", page: "research/backtest" },
] as const;

export const paths = [
  {
    id: "quickstart",
    label: "01 / GET STARTED",
    page: "getting-started/quickstart",
  },
  {
    id: "agent-overview",
    label: "02 / AGENT DEVELOPMENT",
    page: "agent/overview",
  },
  {
    id: "research-overview",
    label: "03 / RESEARCH",
    page: "research/overview",
  },
] as const;

export const journeys = [
  { id: "agent-external", label: "AGENT", page: "agent/external" },
  {
    id: "research-experiments",
    label: "EXPERIMENT",
    page: "research/experiments",
  },
  {
    id: "guides-remote-machines",
    label: "OPERATIONS",
    page: "guides/remote-machines",
  },
  { id: "dev_guide", label: "DEVELOP", page: "dev_guide" },
] as const;

export const screens = [
  {
    id: "lineage",
    image: lineage,
    page: "concepts/task-lineage",
    label: "TASK LINEAGE",
    width: 796,
    height: 442,
  },
  {
    id: "training",
    image: training,
    page: "research/results",
    label: "MODEL TRAINING",
    width: 1190,
    height: 532,
  },
  {
    id: "backtest",
    image: backtest,
    page: "research/backtest",
    label: "BACKTESTING",
    width: 1190,
    height: 388,
  },
  {
    id: "comparison",
    image: comparison,
    page: "research/strategy-comparison",
    label: "STRATEGY COMPARISON",
    width: 1168,
    height: 630,
  },
] as const;

export const capabilities = [
  { id: "plugins-management", label: "PLUGIN", page: "plugins/management" },
  {
    id: "concepts-task-lifecycle",
    label: "TASK",
    page: "concepts/task-lifecycle",
  },
  {
    id: "guides-remote-machines",
    label: "MACHINE",
    page: "guides/remote-machines",
  },
  { id: "api-overview", label: "JOB API", page: "api/overview" },
] as const;

export const benchmarkFigures = [
  { id: "signal", image: signalQuality },
  { id: "portfolio", image: portfolioResults },
] as const;
