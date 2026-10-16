// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { seed } from "../../playground/fixtures";
import { createPlayground } from "../../playground/runtime";
import { AxonXClient, configureClient } from "../../shared/api/client";
import ReportPage from "../operations/ReportPage";
import { parseHistory, parseStockReport } from "./report";

vi.mock("../research/backtest/BacktestChart", () => ({
  BacktestChart: ({ rows }: { rows: unknown[] }) => (
    <div data-chart-rows={rows.length} />
  ),
}));
let root: Root;
let container: HTMLDivElement;
const taskId = "inference#playground_online#demo";
const click = async (text: string) => {
  const button = [
    ...container.querySelectorAll<HTMLButtonElement>("button"),
  ].find((item) => item.textContent === text);
  expect(button).toBeDefined();
  await act(async () => button!.click());
};
beforeEach(() => {
  (
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  configureClient(new AxonXClient(createPlayground(), false));
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  configureClient(new AxonXClient());
});

it.each(
  ["en", "zh"].flatMap((language) =>
    ["light", "dark"].map((theme) => [language, theme]),
  ),
)(
  "shows signals, portfolio, performance and revisions in %s / %s",
  async (language, theme) => {
    await i18n.changeLanguage(language);
    document.documentElement.dataset.theme = theme;
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 390,
    });
    await act(async () =>
      root.render(<ReportPage taskId={taskId} onOpenTask={vi.fn()} />),
    );
    expect(container.textContent).toContain("Synthetic 1");
    expect(container.textContent).toContain(
      i18n.t("onlineReport.columns.rank_change"),
    );
    expect(container.querySelectorAll("tbody tr")).toHaveLength(30);
    await act(async () =>
      container
        .querySelector<HTMLInputElement>('input[type="checkbox"]')!
        .click(),
    );
    expect(container.querySelectorAll("tbody tr")).toHaveLength(25);
    await click(i18n.t("onlineReport.tabs.portfolio"));
    expect(container.textContent).toContain(i18n.t("onlineReport.simulated"));
    expect(container.textContent).toContain(
      i18n.t("onlineReport.values.not_buyable"),
    );
    await click(i18n.t("onlineReport.tabs.performance"));
    expect(container.querySelectorAll("[data-chart-rows]")).toHaveLength(3);
    expect(container.textContent).toContain(
      i18n.t("onlineReport.labelsPending"),
    );
    await click(i18n.t("onlineReport.tabs.history"));
    expect(container.querySelectorAll(".online-revision")).toHaveLength(13);
    expect(container.textContent).toContain(i18n.t("onlineReport.superseded"));
    await act(async () =>
      container
        .querySelectorAll<HTMLButtonElement>(".online-revision")[1]
        .click(),
    );
    expect(container.textContent).toContain(i18n.t("onlineReport.stale"));
    await click(i18n.t("onlineReport.tabs.runtime"));
    expect(container.textContent).toContain(i18n.t("onlinePipeline.windows"));
  },
);

it("rejects corrupt history, incomplete reports and unsafe artifact paths", () => {
  const parsed = parseStockReport(
    seed().tasks.get(taskId)!.output_params.report,
  );
  const invalid = structuredClone(parsed);
  invalid.commit.artifacts.signal.path = "../escape.parquet";
  expect(() => parseStockReport(invalid)).toThrow();
  delete invalid.commit.artifacts.signal;
  expect(() => parseStockReport(invalid)).toThrow("Missing online artifact");
  expect(() =>
    parseHistory({
      version: 1,
      kind: "online_history",
      task_type: "inference",
      strategy_identity: "a".repeat(64),
      commits: [parsed.commit, parsed.commit],
    }),
  ).toThrow("Invalid online revisions");
});

it("uses the latest manifest commit when lifecycle metadata still points to an older revision", async () => {
  const transport = createPlayground();
  configureClient(
    new AxonXClient(async (url, init) => {
      const response = await transport(url, init);
      if (url === "/jobs/status") {
        const payload = await response.json();
        const report = payload.answer.output_params.report;
        if (report) {
          report.commit = {
            ...report.commit,
            commit_id: "f".repeat(32),
            revision: 1,
          };
        }
        return new Response(JSON.stringify(payload), {
          headers: { "Content-Type": "application/json" },
        });
      }
      return response;
    }, false),
  );
  await act(async () =>
    root.render(<ReportPage taskId={taskId} onOpenTask={vi.fn()} />),
  );
  expect(
    container.querySelector<HTMLSelectElement>(
      ".online-report-toolbar select:nth-of-type(1)",
    )?.value,
  ).not.toBe("f".repeat(32));
  const selects = container.querySelectorAll<HTMLSelectElement>(
    ".online-report-toolbar select",
  );
  expect(selects[1].selectedOptions[0].textContent).toContain("r2");
});

it("rejects conflicting report settings and invalid signal dates", () => {
  const report = parseStockReport(
    seed().tasks.get(taskId)!.output_params.report,
  );
  const conflicting = structuredClone(report);
  Object.assign(conflicting, { portfolio: { holding_days: 100 } });
  expect(() => parseStockReport(conflicting)).toThrow(
    "Invalid stock online report",
  );
  const invalid = structuredClone(report);
  invalid.commit.trade_date = "20260230";
  expect(() => parseStockReport(invalid)).toThrow("Invalid online commit");
});

it("rejects the former online signals protocol", () => {
  const report = parseStockReport(
    seed().tasks.get(taskId)!.output_params.report,
  );
  const invalid = structuredClone(report) as unknown as Record<string, unknown>;
  delete (invalid.commit as { protocol: { report: Record<string, unknown> } })
    .protocol.report.signals_format;
  expect(() => parseStockReport(invalid)).toThrow();
});
