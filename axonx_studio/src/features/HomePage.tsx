import { Activity, ArrowRight, Send } from "lucide-react";
import type { Language } from "../types";

export function HomePage({
  language,
  onNavigate,
}: {
  language: Language;
  onNavigate: (page: "submit" | "tasks") => void;
}) {
  const zh = language === "zh";
  return (
    <section className="workspace-page overview-page">
      <div className="overview-hero">
        <div className="hero-copy">
          <p className="eyebrow">AXONX · QUANT</p>
          <h1>
            {zh ? "量化 Harness 框架" : "A harness for quantitative workflows"}
          </h1>
          <p>
            {zh
              ? "组织数据、研究、训练、预测与回测，并交给隔离的 Task Runtime 执行。"
              : "Organize data, research, training, prediction, and backtesting through isolated Task runtimes."}
          </p>
          <div className="hero-actions">
            <button
              className="primary-button"
              onClick={() => onNavigate("submit")}
            >
              <Send />
              {zh ? "提交Task" : "Submit Task"}
              <ArrowRight />
            </button>
            <button
              className="secondary-button"
              onClick={() => onNavigate("tasks")}
            >
              <Activity />
              {zh ? "查看运行" : "View runs"}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
