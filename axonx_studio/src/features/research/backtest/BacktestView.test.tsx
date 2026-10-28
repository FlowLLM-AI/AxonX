import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "../../../i18n";
import { taskStatus } from "../../../playground/data";
import { BacktestView } from "./BacktestView";
import { loadBacktest } from "./api";
import type {
  BacktestArtifact,
  ChartRow,
  ChartSeries,
  DailyRow,
} from "./types";

// @vitest-environment jsdom

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
  ...taskStatus("backtest", "backtest#demo"),
  created_at: "",
  reg_name: "backtest",
  task_type: "backtest",
  output_params: {
    protocol: { version: 1, task_type: "backtest" },
    signals_format: "stock-signals-v1",
    default_universe: "all",
    universes: {
      all: {
        label: "All market",
        parameters: {},
        dimensions: {
          top_ns: [1, 3],
          holding_detail_top_n: 30,
          benchmarks: [],
        },
        date_range: { start: "20260105", end: "20260105" },
        days: 1,
        evaluation_status: "incomplete_market_data",
        artifacts: { daily: "all_daily", summary: "all_summary" },
      },
    },
    artifacts: {},
  },
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
      expect(loadBacktest).toHaveBeenCalledWith(meta, "all", {
        target: "remote",
        signal: expect.any(AbortSignal),
      });
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

  it.each(["en", "zh"])(
    "labels and sorts every benchmark IR and relative drawdown in %s",
    async (language) => {
      await i18n.changeLanguage(language);
      vi.mocked(loadBacktest).mockResolvedValue({
        daily,
        summary: [
          {
            period_type: "overall",
            period: "overall",
            period_start: "20260105",
            period_end: "20260105",
            trading_days: 1,
            ic_mean: 0,
            icir: 0,
            rank_ic_mean: 0,
            rank_icir: 0,
            top1_information_ratio_universe: 1.4,
            top3_information_ratio_custom: 2.3,
            top1_net_relative_max_drawdown_universe: -0.125,
            top3_net_relative_max_drawdown_custom: -0.2345,
          },
        ],
      });
      await act(async () =>
        root.render(
          <BacktestView
            meta={{
              ...meta,
              output_params: {
                ...meta.output_params,
                universes: {
                  ...meta.output_params.universes,
                  all: {
                    ...meta.output_params.universes.all,
                    dimensions: {
                      ...meta.output_params.universes.all.dimensions,
                      benchmarks: [
                        { key: "universe", label: "universe" },
                        { key: "custom", label: "Custom index" },
                      ],
                    },
                  },
                },
              },
            }}
          />,
        ),
      );
      await act(async () =>
        Array.from(
          container.querySelectorAll<HTMLButtonElement>(
            ".backtest-tabs button",
          ),
        )
          .find((button) => button.textContent === i18n.t("backtest.overall"))!
          .click(),
      );
      expect(container.textContent).not.toContain("backtest.metrics.");
      expect(container.textContent).toContain("-12.50%");
      expect(container.textContent).toContain("-23.45%");
      for (const label of [
        "IR · universe",
        "IR · Custom index",
        `${i18n.t("backtest.net_relative_max_drawdown")} · universe`,
        `${i18n.t("backtest.net_relative_max_drawdown")} · Custom index`,
      ]) {
        const button = Array.from(
          container.querySelectorAll<HTMLButtonElement>(".summary-sort-button"),
        ).find((button) => button.textContent === label)!;
        expect(button.getAttribute("aria-label")).toContain(label);
        await act(async () => button.click());
        expect(button.closest("th")?.getAttribute("aria-sort")).toBe(
          "ascending",
        );
      }
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
      root.render(
        <BacktestView meta={{ ...meta, task_id: "backtest#other" }} />,
      ),
    );
    expect(container.textContent).toContain("Service offline");
  });
});

it("switches complete universe reports and reuses cached data", async () => {
  const multi = {
    ...meta,
    output_params: {
      ...meta.output_params,
      universes: {
        ...meta.output_params.universes,
        hs300: { ...meta.output_params.universes.all, label: "HS300" },
      },
    },
  };
  await act(async () =>
    root.render(<BacktestView meta={multi} target="remote" />),
  );
  const select = container.querySelector("select")!;
  const firstSignal = vi.mocked(loadBacktest).mock.calls[0][2]!.signal!;
  await act(async () => {
    select.value = "hs300";
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(firstSignal.aborted).toBe(true);
  expect(loadBacktest).toHaveBeenLastCalledWith(multi, "hs300", {
    target: "remote",
    signal: expect.any(AbortSignal),
  });
  await act(async () => {
    select.value = "all";
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(loadBacktest).toHaveBeenCalledTimes(2);
});

it("ignores a stale universe response after selection changes", async () => {
  let finish!: (value: { daily: DailyRow[]; summary: [] }) => void;
  vi.mocked(loadBacktest).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const multi = {
    ...meta,
    output_params: {
      ...meta.output_params,
      universes: {
        ...meta.output_params.universes,
        hs300: { ...meta.output_params.universes.all, label: "HS300" },
      },
    },
  };
  await act(async () => root.render(<BacktestView meta={multi} />));
  const select = container.querySelector("select")!;
  await act(async () => {
    select.value = "hs300";
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await act(async () => finish({ daily: [], summary: [] }));
  expect(container.querySelector("select")?.value).toBe("hs300");
  expect(container.querySelector(".backtest-report")).not.toBeNull();
});
