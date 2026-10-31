import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { Select } from "../../shared/ui/Select";
import { loadPortfolioSignals } from "./api";
import { PortfolioSelector } from "./PortfolioSelector";
import type { ResearchTask } from "./types";

export function PortfolioView({
  meta,
  target,
}: {
  meta: ResearchTask<"portfolio">;
  target?: string;
}) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState("0");
  const [day, setDay] = useState("");
  const plan = meta.output_params.portfolios[Number(selected)];
  const topN = Number(plan?.portfolio_id.top_n);
  const load = useCallback(
    (signal: AbortSignal) => {
      return loadPortfolioSignals(meta, Number(selected), { target, signal });
    },
    [meta, selected, target],
  );
  const { data, error, loading } = useAsyncResource(load);
  const dates = [...new Set(data?.map((row) => row.trade_date) || [])].sort();
  const selectedDate = dates.includes(day) ? day : dates.at(-1) || "";
  const visible = data
    ?.filter(
      (row) =>
        row.trade_date === selectedDate &&
        row.is_portfolio_candidate &&
        row.target_rank !== null &&
        row.target_rank <= topN,
    )
    .sort((left, right) => left.target_rank! - right.target_rank!);
  return (
    <section className="viz-card wide portfolio-view">
      <PortfolioSelector
        portfolios={meta.output_params.portfolios}
        value={selected}
        onChange={setSelected}
      />
      <section className="portfolio-targets">
        <header>
          <h3>{t("portfolio.targets")}</h3>
          <Select
            aria-label={t("portfolio.date")}
            value={selectedDate}
            onChange={(event) => setDay(event.target.value)}
          >
            {dates.map((date) => (
              <option key={date} value={date}>
                {date}
              </option>
            ))}
          </Select>
        </header>
        {error ? (
          <div role="alert">{error}</div>
        ) : loading ? (
          <div aria-busy="true">…</div>
        ) : !visible?.length ? (
          <p>{t("portfolio.empty")}</p>
        ) : (
          <div className="compare-table-wrap">
            <table className="compare-table">
              <thead>
                <tr>
                  {["date", "code", "rank", "weight"].map((key) => (
                    <th key={key}>{t(`portfolio.${key}`)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible?.map((row) => (
                  <tr
                    key={`${row.trade_date}:${row.trade_time}:${row.ts_code}`}
                  >
                    <td>
                      {row.trade_date} {row.trade_time}
                    </td>
                    <td>{row.ts_code}</td>
                    <td>{row.target_rank}</td>
                    <td>{(100 / topN).toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </section>
  );
}
