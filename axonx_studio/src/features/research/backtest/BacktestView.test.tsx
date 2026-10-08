// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "../../../i18n";
import { BacktestView } from "./BacktestView";
import { loadBacktest } from "./api";
import type {
  BacktestArtifact,
  ChartRow,
  ChartSeries,
  DailyRow,
} from "./types";

vi.mock("./api", () => ({ loadBacktest: vi.fn() }));
vi.mock("./BacktestChart", () => ({
  BacktestChart: ({
    rows,
    series,
  }: {
    rows: ChartRow[];
    series: ChartSeries[];
  }) => (
    <div data-chart={JSON.stringify({ rows, series })}>
      {series.map((s) => s.label).join(" ")}
    </div>
  ),
}));
const meta: BacktestArtifact = {
  _path: "backtest/demo",
  task_key: "backtest",
  created_at: "",
  config: {
    task_id: "backtest#demo",
    task_type: "backtest",
    task_name: "demo",
  },
  dimensions: { top_ns: [1, 3], holding_detail_top_n: 30, benchmarks: [] },
  artifacts: {},
  evaluation_status: "incomplete_market_data",
};
const daily: DailyRow[] = [
  {
    trade_date: "20260105",
    candidate_count: 1,
    ic: null,
    rank_ic: null,
    top1_net_return: 0,
    top3_net_return: 0,
    top1_ndcg: 0.5,
    top3_ndcg: 0.75,
    top30_holdings: [
      {
        rank: 1,
        ts_code: "A",
        name: "A",
        prediction: 0.2,
        daily_return: null,
        weight: 1,
      },
    ],
  },
];
let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(loadBacktest).mockResolvedValue({ daily, summary: [] });
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});
const render = async () => {
  await act(async () =>
    root.render(<BacktestView meta={meta} target="remote" />),
  );
};
describe("stock backtest report", () => {
  it.each(["en", "zh"])(
    "renders dynamic NDCG and provisional evaluation in %s",
    async (language) => {
      await i18n.changeLanguage(language);
      await render();
      expect(container.querySelector('[role="alert"]')?.textContent).toContain(
        i18n.t("backtest.incomplete_market_data"),
      );
      expect(loadBacktest).toHaveBeenCalledWith(
        meta,
        "remote",
        expect.any(AbortSignal),
      );
      expect(container.querySelector("td.positive, td.negative")).toBeNull();
      await act(async () =>
        Array.from(
          container.querySelectorAll<HTMLButtonElement>(
            ".backtest-tabs button",
          ),
        )
          .find(
            (button) => button.textContent === i18n.t("backtest.model_quality"),
          )!
          .click(),
      );
      expect(container.textContent).toContain("NDCG@1");
      expect(container.textContent).toContain("NDCG@3");
      expect(container.textContent).not.toContain("NDCG@15");
      const chart = Array.from(
        container.querySelectorAll<HTMLElement>("[data-chart]"),
      )
        .map((element) => JSON.parse(element.dataset.chart!))
        .find((chart) => chart.series[0]?.label === "NDCG@1");
      expect(chart.rows[0]).toMatchObject({ ndcg_1: 0.5, ndcg_3: 0.75 });
    },
  );

  it("renders empty data and request failures", async () => {
    vi.mocked(loadBacktest).mockResolvedValue({ daily: [], summary: [] });
    await render();
    expect(container.textContent).toContain(
      i18n.t("backtest.daily_parquet_is_empty"),
    );
    vi.mocked(loadBacktest).mockRejectedValue(new Error("Service offline"));
    await act(async () =>
      root.render(<BacktestView meta={{ ...meta, _path: "other" }} />),
    );
    expect(container.textContent).toContain("Service offline");
  });
});
