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
import { useTranslation } from "react-i18next";

const quantSteps: SectionId[] = [
  "raw",
  "etl",
  "factors",
  "train",
  "predict",
  "backtest",
];

const harnessFeatures = [
  {
    icon: Puzzle,
    code: "PLUGIN",
    id: "plugin",
  },
  {
    icon: Network,
    code: "MACHINE",
    id: "machine",
  },
  {
    icon: FileCode2,
    code: "JOB",
    id: "job",
  },
  {
    icon: Activity,
    code: "TASK",
    id: "task",
  },
  {
    icon: Box,
    code: "WORKSPACE",
    id: "workspace",
  },
  {
    icon: GitBranch,
    code: "LINEAGE",
    id: "lineage",
  },
];

function QuantIcon({ id }: { id: SectionId }) {
  const Icon = navigationItems.find((item) => item.id === id)?.icon;
  return Icon ? <Icon aria-hidden="true" /> : null;
}

export function HomePage({
  onNavigate,
}: {
  onNavigate: (page: "submit" | "tasks" | SectionId) => void;
}) {
  const { t } = useTranslation();
  return (
    <section className="workspace-page overview-page">
      <div className="overview-hero">
        <section className="hero-quant" aria-label={t("home.quantAria")}>
          <div className="hero-quant-heading">
            <span>01 / QUANT RESEARCH</span>
            <h2>{t("home.quantTitle")}</h2>
            <p>{t("home.quantLead")}</p>
          </div>
          <ol className="hero-quant-steps">
            {quantSteps.map((step, index) => (
              <li key={step}>
                <button
                  className={`hero-quant-step hero-quant-${step}`}
                  onClick={() => onNavigate(step)}
                >
                  <span className="hero-quant-icon">
                    <QuantIcon id={step} />
                  </span>
                  <span className="hero-quant-step-copy">
                    <strong>{t(`home.steps.${step}.title`)}</strong>
                    <small>{t(`home.steps.${step}.detail`)}</small>
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

        <section className="hero-brand" aria-label={t("home.brandAria")}>
          <div className="hero-brand-halo" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <div className="hero-brand-content">
            <span className="hero-brand-kicker">AXONX / QUANT HARNESS</span>
            <img src="/axonx-logo.svg" alt="AxonX" />
            <h1>{t("home.brandTitle")}</h1>
            <p>{t("home.brandLead")}</p>
            <div className="hero-brand-actions">
              <button
                className="primary-button"
                onClick={() => onNavigate("submit")}
              >
                <Send aria-hidden="true" />
                {t("home.submitTask")}
                <ArrowRight aria-hidden="true" />
              </button>
              <button
                className="secondary-button"
                onClick={() => onNavigate("tasks")}
              >
                <Activity aria-hidden="true" />
                {t("home.manageTasks")}
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
          aria-label={t("home.capabilitiesAria")}
        >
          <div className="hero-harness-heading">
            <span>02 / HARNESS CORE</span>
            <h2>{t("home.capabilitiesTitle")}</h2>
            <p>{t("home.capabilitiesLead")}</p>
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
                    <strong>{t(`home.features.${feature.id}.title`)}</strong>
                    <small>{t(`home.features.${feature.id}.detail`)}</small>
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
