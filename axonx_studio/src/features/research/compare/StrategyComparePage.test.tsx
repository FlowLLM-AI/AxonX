import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import i18n from "../../../i18n";
import { table } from "../../../playground/data";
import { axonx } from "../../../shared/api/client";
import { previewWorkspaceFile } from "../../../shared/api/workspace";
import StrategyComparePage from "./StrategyComparePage";

// @vitest-environment jsdom

vi.mock("../../../shared/api/client", () => ({ axonx: { invoke: vi.fn() } }));
vi.mock("../../../shared/api/workspace", () => ({
  previewWorkspaceFile: vi.fn(),
}));
vi.mock("../backtest/BacktestChart", () => ({ BacktestChart: () => null }));
let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.clearAllMocks();
  container = document.createElement("div");
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
});

it.each(["en", "zh"])(
  "compares current source and replica signals on the selected machine in %s",
  async (language) => {
    await i18n.changeLanguage(language);
    vi.mocked(previewWorkspaceFile).mockImplementation(async ({ path }) => {
      if (!path.endsWith("metadata.json"))
        return table([
          {
            trade_date: "20260105",
            top1_net_return: 0.01,
            top3_net_return: 0.02,
          },
        ]);
      const name = path.split("/")[1];
      const file = { path: "daily.parquet", size: 1, revision: "1:1" };
      return {
        kind: "json",
        size: 1,
        content: "",
        parse_error: null,
        truncated: false,
        data: {
          task_id: `backtest#${name}`,
          reg_name: name,
          state: "succeeded",
          created_at: "20260105",
          input_params: { task_name: name },
          output_params: {
            signals_format: "stock-signals-v3",
            portfolios: [1, 3].map((n) => ({
              portfolio_id: { universe: { kind: "all" }, top_n: n },
              dimensions: {
                top_ns: [n],
                holding_detail_top_n: 1,
                benchmarks: [],
              },
              date_range: {},
              days: 1,
              evaluation_status: "done",
              artifacts: { daily: "daily", summary: "summary" },
            })),
            artifacts: {
              daily: file,
              summary: { ...file, path: "summary.parquet" },
              signals: { ...file, path: "signals.parquet" },
            },
          },
          replica:
            name === "b"
              ? {
                  purpose: "display",
                  files: { "daily.parquet": { size: 2, revision: "replica" } },
                  omitted: { "signals.parquet": "budget" },
                }
              : null,
        },
      };
    });
    vi.mocked(axonx.invoke).mockImplementation(async (job, args) => {
      const values = await Promise.all(
        ["a", "b"].map(async (name) => {
          const preview = await previewWorkspaceFile(
            { path: `tasks/backtest/${name}/metadata.json` },
            {},
          );
          if (preview?.kind !== "json") throw new Error("Expected metadata");
          return {
            ...(preview.data as Record<string, unknown>),
            task_id: `backtest#${name}`,
            task_type: "backtest",
          };
        }),
      );
      return job === "status"
        ? values.find((item) => item.task_id === args?.task_id)!
        : values;
    });
    await act(async () =>
      root.render(
        <StrategyComparePage target="remote" onConnection={vi.fn()} />,
      ),
    );
    for (const button of container.querySelectorAll<HTMLButtonElement>(
      ".compare-task-item",
    )) {
      await act(async () => button.click());
    }
    expect(container.textContent).not.toContain(
      i18n.t("backtest.errors.signalsFormat"),
    );
    expect(container.querySelector(".compare-tabs")).not.toBeNull();
    const topA = container.querySelector<HTMLSelectElement>(
      'select[aria-label$=" A · top_n"]',
    )!;
    const topB = container.querySelector<HTMLSelectElement>(
      'select[aria-label$=" B · top_n"]',
    )!;
    await act(async () => {
      topB.value = "3";
      topB.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(topA.value).toBe("1");
    expect(topB.value).toBe("3");
    expect(container.querySelector(".compare-tabs")).not.toBeNull();
    for (const name of ["a", "b"]) {
      expect(previewWorkspaceFile).toHaveBeenCalledWith(
        {
          path: `tasks/backtest/backtest#${name}/daily.parquet`,
          offset: 0,
          limit: 5000,
        },
        { target: "remote", signal: expect.any(AbortSignal) },
      );
    }
  },
);

it("loads only selected details and displays detail failures", async () => {
  vi.mocked(axonx.invoke).mockImplementation(async (job) => {
    if (job === "status") throw new Error("Detail service offline");
    return ["a", "b"].map((name) => ({
      task_id: `backtest#${name}`,
      reg_name: name,
      display_name: name,
      started_at: name,
      task_type: "backtest",
      state: "succeeded",
    }));
  });
  await act(async () =>
    root.render(<StrategyComparePage target="remote" onConnection={vi.fn()} />),
  );
  expect(
    vi.mocked(axonx.invoke).mock.calls.filter(([job]) => job === "status"),
  ).toHaveLength(0);
  await act(async () =>
    container.querySelector<HTMLButtonElement>(".compare-task-item")!.click(),
  );
  const detailCalls = vi
    .mocked(axonx.invoke)
    .mock.calls.filter(([job]) => job === "status");
  expect(detailCalls).toHaveLength(1);
  expect(detailCalls[0][1]).toEqual({ task_id: "backtest#a" });
  expect(container.querySelector('[role="alert"]')?.textContent).toContain(
    "Detail service offline",
  );
});

it("does not request old task IDs from a newly selected machine while its list is pending", async () => {
  const onConnection = vi.fn();
  vi.mocked(axonx.invoke).mockImplementation(async (job, _args, options) => {
    if (job === "status") throw new Error("not requested in this test");
    if (options?.target === "machine-b") return new Promise(() => {});
    return [
      {
        task_id: "backtest#only-a",
        reg_name: "only-a",
        display_name: "only-a",
        task_type: "backtest",
        started_at: "a",
        state: "succeeded",
      },
    ];
  });
  await act(async () =>
    root.render(
      <StrategyComparePage
        target="machine-a"
        initialTaskId="backtest#only-a"
        onConnection={onConnection}
      />,
    ),
  );
  vi.mocked(axonx.invoke).mockClear();
  await act(async () =>
    root.render(
      <StrategyComparePage
        target="machine-b"
        initialTaskId="backtest#only-a"
        onConnection={onConnection}
      />,
    ),
  );
  expect(
    vi.mocked(axonx.invoke).mock.calls.filter(([job]) => job === "status"),
  ).toHaveLength(0);
});
