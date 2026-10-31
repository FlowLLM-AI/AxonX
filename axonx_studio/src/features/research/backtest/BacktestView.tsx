import { AlertTriangle, LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { BacktestPortfolioReport } from "../../../shared/api/contracts";
import { taskDirectory } from "../../../shared/lib/tasks";
import { PortfolioSelector } from "../PortfolioSelector";
import { loadBacktest } from "./api";
import { Overview } from "./BacktestOverview";
import { SummaryView } from "./BacktestSummary";
import type { BacktestArtifact, DailyRow, SummaryRow } from "./types";

export function BacktestView({
  meta,
  target,
}: {
  meta: BacktestArtifact;
  target?: string;
}) {
  return (
    <PortfolioBacktest
      key={`${target || ""}:${taskDirectory(meta.task_id)}:${meta.started_at}`}
      meta={meta}
      target={target}
    />
  );
}

function PortfolioBacktest({
  meta,
  target,
}: {
  meta: BacktestArtifact;
  target?: string;
}) {
  const { t } = useTranslation();
  const [universe, setUniverse] = useState("0");
  const cache = useRef(
    new Map<string, { daily: DailyRow[]; summary: SummaryRow[] }>(),
  );
  const report = meta.output_params.portfolios[Number(universe)];
  const [daily, setDaily] = useState<DailyRow[]>([]);
  const [summary, setSummary] = useState<SummaryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setDaily([]);
    setSummary([]);
    const cached = cache.current.get(universe);
    if (cached) {
      setDaily(cached.daily);
      setSummary(cached.summary);
      setLoading(false);
      return () => controller.abort();
    }
    loadBacktest(meta, universe, { target, signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        cache.current.set(universe, data);
        setDaily(data.daily);
        setSummary(data.summary);
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => !controller.signal.aborted && setLoading(false));
    return () => controller.abort();
  }, [meta, target, universe]);

  return (
    <section>
      <PortfolioSelector
        portfolios={meta.output_params.portfolios}
        value={universe}
        onChange={setUniverse}
      />
      {report && (
        <div className="backtest-report-dates">
          {report.date_range.start} – {report.date_range.end} · {report.days}{" "}
          {t("backtest.days")}
        </div>
      )}
      {loading ? (
        <div className="research-loading">
          <LoaderCircle className="spin" />
        </div>
      ) : error || !report || !daily.length ? (
        <div className="data-gap">
          <AlertTriangle />
          <strong>{t("backtest.unable_to_load_backtest_artifacts")}</strong>
          <span>{error || t("backtest.daily_parquet_is_empty")}</span>
        </div>
      ) : (
        <BacktestReport
          key={universe}
          meta={report}
          daily={daily}
          summary={summary}
        />
      )}
    </section>
  );
}

function BacktestReport({
  meta,
  daily,
  summary,
}: {
  meta: BacktestPortfolioReport;
  daily: DailyRow[];
  summary: SummaryRow[];
}) {
  const { t } = useTranslation();
  const topNs = meta.dimensions.top_ns;
  const benchmarks = meta.dimensions.benchmarks;
  const [tab, setTab] = useState<
    "gross" | "net" | "quality" | "overall" | "year" | "quarter" | "month"
  >("gross");
  const [range, setRange] = useState<[number, number]>([0, daily.length - 1]);
  const [hoveredDate, setHoveredDate] = useState("");
  const [lockedDate, setLockedDate] = useState("");
  const tabs = [
    ["gross", t("backtest.gross_return")],
    ["net", t("backtest.net_return")],
    ["quality", t("backtest.model_quality")],
    ["overall", t("backtest.overall")],
    ["year", t("backtest.yearly")],
    ["quarter", t("backtest.quarterly")],
    ["month", t("backtest.monthly")],
  ];
  return (
    <div className="backtest-report">
      {meta.evaluation_status === "incomplete_market_data" && (
        <div className="data-gap" role="alert">
          <AlertTriangle />
          <span>{t("backtest.incomplete_market_data")}</span>
        </div>
      )}
      <nav className="backtest-tabs">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            className={tab === key ? "active" : ""}
            onClick={() => setTab(key as typeof tab)}
          >
            {label}
          </button>
        ))}
      </nav>
      {tab === "gross" || tab === "net" || tab === "quality" ? (
        <Overview
          view={tab}
          daily={daily}
          topNs={topNs}
          benchmarks={benchmarks}
          range={range}
          setRange={setRange}
          hoveredDate={hoveredDate}
          setHoveredDate={setHoveredDate}
          lockedDate={lockedDate}
          setLockedDate={setLockedDate}
        />
      ) : (
        <SummaryView
          rows={summary.filter((row) => row.period_type === tab)}
          topNs={topNs}
          benchmarks={benchmarks}
        />
      )}
    </div>
  );
}
