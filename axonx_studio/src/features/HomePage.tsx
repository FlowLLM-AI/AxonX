import {
  Activity,
  ArrowDown,
  ArrowRight,
  Box,
  FileCode2,
  GitBranch,
  Network,
  Puzzle,
  Send,
} from "lucide-react";
import { navigationItems } from "../app/navigation";
import type { SectionId } from "../app/routes";
import type { Language } from "../app/types";

const quantSteps: {
  id: SectionId;
  zh: string;
  en: string;
  detailZh: string;
  detailEn: string;
}[] = [
  {
    id: "raw",
    zh: "Tushare 数据",
    en: "Market data",
    detailZh: "行情与基础数据",
    detailEn: "Prices and fundamentals",
  },
  {
    id: "etl",
    zh: "ETL 特征构建",
    en: "ETL features",
    detailZh: "清洗数据，生成特征",
    detailEn: "Clean data and build features",
  },
  {
    id: "factors",
    zh: "因子分析",
    en: "Factor analysis",
    detailZh: "检验因子表现",
    detailEn: "Evaluate factor performance",
  },
  {
    id: "train",
    zh: "模型训练",
    en: "Model training",
    detailZh: "拟合模型，评估效果",
    detailEn: "Fit and evaluate models",
  },
  {
    id: "predict",
    zh: "离线预测",
    en: "Prediction",
    detailZh: "生成预测结果",
    detailEn: "Generate predictions",
  },
  {
    id: "backtest",
    zh: "离线回测",
    en: "Backtesting",
    detailZh: "验证策略表现",
    detailEn: "Validate strategy performance",
  },
];

const harnessFeatures = [
  {
    icon: Puzzle,
    code: "PLUGIN",
    zh: "插件化扩展",
    en: "Plugin extensions",
    detailZh: "自动安装 · 支持远端安装",
    detailEn: "Auto install · remote install support",
  },
  {
    icon: Network,
    code: "MACHINE",
    zh: "多机器节点",
    en: "Multiple machines",
    detailZh: "节点发现 · 健康检查",
    detailEn: "Node discovery · health checks",
  },
  {
    icon: FileCode2,
    code: "JOB",
    zh: "声明式 Job 接口",
    en: "Declarative Job API",
    detailZh: "参数 Schema · 可组合 Steps",
    detailEn: "Parameter schemas · composed steps",
  },
  {
    icon: Activity,
    code: "TASK",
    zh: "Task 生命周期",
    en: "Task lifecycle",
    detailZh: "提交 · 状态 · 日志 · 取消",
    detailEn: "Submit · status · logs · cancel",
  },
  {
    icon: Box,
    code: "WORKSPACE",
    zh: "工作区管理",
    en: "Workspace management",
    detailZh: "目录浏览 · 文件预览与清理",
    detailEn: "Browse · preview · cleanup",
  },
  {
    icon: GitBranch,
    code: "LINEAGE",
    zh: "产物关系图",
    en: "Artifact lineage",
    detailZh: "跨任务搜索 · 上下游追踪",
    detailEn: "Cross-task search · dependency tracing",
  },
];

function QuantIcon({ id }: { id: SectionId }) {
  const Icon = navigationItems.find((item) => item.id === id)?.icon;
  return Icon ? <Icon aria-hidden="true" /> : null;
}

export function HomePage({
  language,
  onNavigate,
}: {
  language: Language;
  onNavigate: (page: "submit" | "tasks" | SectionId) => void;
}) {
  const zh = language === "zh";
  return (
    <section className="workspace-page overview-page">
      <div className="overview-hero">
        <section
          className="hero-quant"
          aria-label={zh ? "量化基础框架" : "Quant research framework"}
        >
          <div className="hero-quant-heading">
            <span>01 / QUANT RESEARCH</span>
            <h2>{zh ? "量化基础框架" : "Quant research"}</h2>
            <p>
              {zh
                ? "从数据准备到策略验证"
                : "From market data to strategy validation"}
            </p>
          </div>
          <ol className="hero-quant-steps">
            {quantSteps.map((step, index) => (
              <li key={step.id}>
                <button
                  className={`hero-quant-step hero-quant-${step.id}`}
                  onClick={() => onNavigate(step.id)}
                >
                  <span className="hero-quant-icon">
                    <QuantIcon id={step.id} />
                  </span>
                  <span className="hero-quant-step-copy">
                    <strong>{zh ? step.zh : step.en}</strong>
                    <small>{zh ? step.detailZh : step.detailEn}</small>
                  </span>
                  <ArrowRight className="hero-quant-open" aria-hidden="true" />
                </button>
                {index < quantSteps.length - 1 && (
                  <ArrowDown
                    className="hero-quant-connector"
                    aria-hidden="true"
                  />
                )}
              </li>
            ))}
          </ol>
        </section>

        <section
          className="hero-brand"
          aria-label={zh ? "AxonX 量化 Harness 框架" : "AxonX Quant Harness"}
        >
          <div className="hero-brand-halo" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <div className="hero-brand-content">
            <span className="hero-brand-kicker">AXONX / QUANT HARNESS</span>
            <img src="/axonx-logo.svg" alt="AxonX" />
            <h1>{zh ? "量化 Harness 框架" : "A harness for quant research"}</h1>
            <p>
              {zh
                ? "用可组合 Task 连接研究能力，让运行、扩展与产物追踪都有统一底座。"
                : "Compose research Tasks on one foundation for execution, extension, and artifact lineage."}
            </p>
            <div className="hero-brand-actions">
              <button
                className="primary-button"
                onClick={() => onNavigate("submit")}
              >
                <Send aria-hidden="true" />
                {zh ? "提交任务" : "Submit Task"}
                <ArrowRight aria-hidden="true" />
              </button>
              <button
                className="secondary-button"
                onClick={() => onNavigate("tasks")}
              >
                <Activity aria-hidden="true" />
                {zh ? "任务管理" : "Manage Tasks"}
              </button>
            </div>
            <div className="hero-brand-footer">
              <span>JOB</span>
              <i />
              <span>TASK</span>
              <i />
              <span>ARTIFACT</span>
            </div>
          </div>
        </section>

        <section
          className="hero-harness"
          aria-label={
            zh ? "Harness 框架能力" : "Harness framework capabilities"
          }
        >
          <div className="hero-harness-heading">
            <span>02 / HARNESS CORE</span>
            <h2>{zh ? "Harness 框架能力" : "Harness capabilities"}</h2>
            <p>
              {zh ? "从插件扩展到产物追踪" : "From plugins to artifact lineage"}
            </p>
          </div>
          <div className="hero-harness-manifest">
            {harnessFeatures.map((feature) => {
              const Icon = feature.icon;
              return (
                <div className="hero-harness-feature" key={feature.code}>
                  <span className="hero-harness-icon">
                    <Icon aria-hidden="true" />
                  </span>
                  <div>
                    <strong>{zh ? feature.zh : feature.en}</strong>
                    <small>{zh ? feature.detailZh : feature.detailEn}</small>
                  </div>
                  <code>{feature.code}</code>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </section>
  );
}
