// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import i18n from "../../../i18n";
import { table } from "../../../playground/fixtures";
import { listTaskRuns, previewWorkspaceFile } from "../../workspace/api";
import StrategyComparePage from "./StrategyComparePage";

vi.mock("../../workspace/api", () => ({
  listTaskRuns: vi.fn(),
  previewWorkspaceFile: vi.fn(),
}));
vi.mock("../backtest/BacktestChart", () => ({ BacktestChart: () => null }));
let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
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
    vi.mocked(listTaskRuns).mockResolvedValue({
      path: "backtest",
      truncated: false,
      entries: ["a", "b"].map((name) => ({
        name,
        path: `backtest/${name}`,
        kind: "directory",
        preview_kind: null,
        supported: true,
        size: null,
        modified_at: 0,
      })),
    });
    vi.mocked(previewWorkspaceFile).mockImplementation(async (path) => {
      if (!path.endsWith("metadata.json"))
        return table([{ trade_date: "20260105", top1_net_return: 0.01 }]);
      const name = path.split("/")[1];
      const file = { path: "daily.parquet", size: 1, sha256: "digest" };
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
            signals_format: "stock-signals-v1",
            dimensions: { top_ns: [1] },
            artifacts: {
              daily: file,
              signals: { ...file, path: "signals.parquet" },
            },
          },
          replica:
            name === "b"
              ? {
                  purpose: "display",
                  files: { "daily.parquet": { size: 2, sha256: "replica" } },
                  omitted: { "signals.parquet": "budget" },
                }
              : null,
        },
      };
    });
    await act(async () =>
      root.render(
        <StrategyComparePage target="remote" onConnection={vi.fn()} />,
      ),
    );
    for (const button of container.querySelectorAll<HTMLButtonElement>(
      ".compare-run-item",
    )) {
      await act(async () => button.click());
    }
    expect(container.textContent).not.toContain(
      i18n.t("backtest.errors.signalsFormat"),
    );
    expect(container.querySelector(".compare-tabs")).not.toBeNull();
    for (const name of ["a", "b"]) {
      expect(previewWorkspaceFile).toHaveBeenCalledWith(
        `backtest/${name}/daily.parquet`,
        0,
        5000,
        "remote",
        expect.any(AbortSignal),
      );
    }
  },
);
