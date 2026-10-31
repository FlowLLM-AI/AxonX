// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { seed } from "../../playground/fixtures";
import { previewWorkspaceFile } from "../../shared/api/workspace";
import { PortfolioView } from "./PortfolioView";
import { restorePortfolioSignals } from "./portfolio";
import type { ResearchTask } from "./types";

vi.mock("../../shared/api/workspace", () => ({
  previewWorkspaceFile: vi.fn(),
}));

it("joins frozen scores and complete ranks by normalized keys without recomputing selection", () => {
  const predictions = ["A", "B"].map((ts_code) => ({
    trade_date: 20240102,
    trade_time: 1445,
    ts_code,
    raw: 100,
    is_buyable_at_signal: true,
  }));
  const rankings = [
    {
      trade_date: "20240102",
      trade_time: "1445",
      ts_code: "B",
      target_rank: 1,
    },
  ];
  const scores = predictions.map((row, i) => ({ ...row, pred: i + 1 }));
  const rows = restorePortfolioSignals(predictions, rankings, "pred", scores);
  expect(
    rows.map((row) => [
      row.ts_code,
      row.pred,
      row.target_rank,
      row.is_portfolio_candidate,
    ]),
  ).toEqual([
    ["B", 2, 1, true],
    ["A", 1, null, false],
  ]);
  expect(rows[0].trade_date).toBe("20240102");
  expect(() =>
    restorePortfolioSignals(predictions, rankings, "pred", []),
  ).toThrow("Missing final portfolio score");
});

it.each(["en", "zh"])(
  "derives portfolio targets from upstream predictions and shared rankings in %s",
  async (language) => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    await i18n.changeLanguage(language);
    const { tasks, files } = seed();
    const meta = tasks.get(
      "portfolio#playground_portfolio#demo",
    ) as ResearchTask<"portfolio">;
    vi.mocked(previewWorkspaceFile).mockImplementation(async ({ path }) =>
      files.get(path)!,
    );
    const container = document.createElement("div");
    const root = createRoot(container);
    try {
      await act(async () =>
        root.render(<PortfolioView meta={meta} target="remote" />),
      );
      expect(container.querySelector("details")).toBeNull();
      expect(container.querySelector("tbody")?.textContent).toContain("20.00%");
      expect(container.querySelectorAll("tbody tr")).toHaveLength(5);
      const select = container.querySelector<HTMLSelectElement>(
        `select[aria-label="${i18n.t("backtest.portfolio")} · top_n"]`,
      )!;
      await act(async () => {
        select.value = "10";
        select.dispatchEvent(new Event("change", { bubbles: true }));
      });
      expect(select.value).toBe("10");
      expect(container.querySelector("tbody")?.textContent).toContain("10.00%");
      expect(container.querySelectorAll("tbody tr")).toHaveLength(10);
      expect(previewWorkspaceFile).toHaveBeenCalledWith(
        expect.objectContaining({
          path: expect.stringContaining("/rankings.parquet"),
        }),
        { target: "remote", signal: expect.any(AbortSignal) },
      );
    } finally {
      await act(async () => root.unmount());
    }
  },
);

it.each([0, 2])(
  "keeps empty and underfilled targets at 1/N weight (%i candidates)",
  async (count) => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    const { tasks, files } = seed();
    const meta = tasks.get(
      "portfolio#playground_portfolio#demo",
    ) as ResearchTask<"portfolio">;
    vi.mocked(previewWorkspaceFile).mockImplementation(async ({ path }) => {
      const preview = files.get(path)!;
      if (preview.kind !== "parquet") return preview;
      const rank = preview.columns.indexOf("target_rank");
      if (rank < 0) return preview;
      return {
        ...preview,
        rows: preview.rows.filter((row) => Number(row[rank]) <= count),
      };
    });
    const container = document.createElement("div");
    const root = createRoot(container);
    try {
      await act(async () => root.render(<PortfolioView meta={meta} />));
      expect(container.querySelectorAll("tbody tr")).toHaveLength(count);
      if (count) {
        expect(container.querySelector("tbody")?.textContent).toContain(
          "20.00%",
        );
      } else {
        expect(container.textContent).toContain(i18n.t("portfolio.empty"));
      }
    } finally {
      await act(async () => root.unmount());
    }
  },
);
