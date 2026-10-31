import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { seed } from "../../playground/fixtures";
import { axonx } from "../../shared/api/client";
import { previewWorkspaceFile } from "../../shared/api/workspace";
import ResearchPage from "./ResearchPage";

// @vitest-environment jsdom

vi.mock("../../shared/api/client", () => ({ axonx: { invoke: vi.fn() } }));
vi.mock("../../shared/api/workspace", () => ({
  previewWorkspaceFile: vi.fn(),
  deleteWorkspaceEntries: vi.fn(),
}));
vi.mock("./TrainingCurveChart", () => ({ TrainingCurveChart: () => null }));
vi.mock("./backtest/BacktestChart", () => ({ BacktestChart: () => null }));

it.each(["en", "zh"])(
  "loads universe metadata through the research index on the selected machine in %s",
  async (language) => {
    await i18n.changeLanguage(language);
    const { files, tasks } = seed();
    vi.mocked(axonx.invoke).mockImplementation(async (name) =>
      name === "status"
        ? tasks.get("backtest#playground_backtest#demo")!
        : [tasks.get("backtest#playground_backtest#demo")!],
    );
    const path = "tasks/backtest/backtest#playground_backtest#demo";
    vi.mocked(previewWorkspaceFile).mockImplementation(
      async ({ path: key }) => {
        const preview = files.get(key);
        if (!preview) throw new Error(`Missing fixture ${key}`);
        return preview;
      },
    );
    const container = document.createElement("div");
    const root = createRoot(container);
    try {
      await act(async () =>
        root.render(
          <ResearchPage
            kind="backtest"
            target="remote"
            initialSelectedId="backtest#playground_backtest#demo"
            onConnection={vi.fn()}
            onNavigate={vi.fn()}
          />,
        ),
      );
      // React.lazy resolves the actual report component after index metadata is read.
      await act(async () => {
        await import("./backtest/BacktestView");
      });
      await vi.waitFor(async () => {
        await act(async () => {});
        expect(
          container.querySelector(".portfolio-selector select"),
        ).not.toBeNull();
      });
      const selector = container.querySelector<HTMLSelectElement>(
        '.portfolio-selector select[aria-label$=" · universe"]',
      );
      expect(selector?.selectedOptions[0].textContent).toBe("all");
      expect(container.querySelector(".base-files-card")).toBeNull();
      expect(container.querySelector(".artifact-kpis")).toBeNull();
      expect(container.textContent).not.toContain(
        i18n.t("backtest.unable_to_load_backtest_artifacts"),
      );
      expect(
        container.querySelector(".backtest-report-dates")?.textContent,
      ).toContain("60");
      await act(async () => {
        selector!.value = selector!.options[1].value;
        selector!.dispatchEvent(new Event("change", { bubbles: true }));
      });
      expect(selector?.selectedOptions[0].textContent).toContain("hs300");
      for (const index of [0, 1]) {
        expect(previewWorkspaceFile).toHaveBeenCalledWith(
          {
            path: `${path}/portfolios/${index}/daily.parquet`,
            offset: 0,
            limit: 5000,
          },
          { target: "remote", signal: expect.any(AbortSignal) },
        );
      }
    } finally {
      await act(async () => root.unmount());
      container.remove();
    }
  },
);

it("reads the model index directly from training metadata", async () => {
  const { files, tasks } = seed();
  const task = tasks.get("train#playground_train#demo")!;
  vi.mocked(axonx.invoke).mockImplementation(async (name) =>
    name === "status" ? task : [task],
  );
  vi.mocked(previewWorkspaceFile).mockImplementation(async ({ path }) => {
    const preview = files.get(path);
    if (!preview) throw new Error(`Missing fixture ${path}`);
    return preview;
  });
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    await act(async () =>
      root.render(
        <ResearchPage
          kind="train"
          target="remote"
          initialSelectedId="train#playground_train#demo"
          onConnection={vi.fn()}
          onNavigate={vi.fn()}
        />,
      ),
    );
    await vi.waitFor(async () => {
      await act(async () => {});
      const card = [
        ...container.querySelectorAll(".artifact-kpis article"),
      ].find((node) =>
        node.textContent?.includes(i18n.t("research.model_members")),
      );
      expect(card?.querySelector("strong")?.textContent).toBe("1");
    });
    expect(previewWorkspaceFile).not.toHaveBeenCalled();
    const selector = container.querySelector<HTMLSelectElement>(
      ".artifact-content select",
    );
    expect(selector?.options).toHaveLength(1);
    expect(selector?.options[0].textContent).toContain("seed_0");
    expect(container.textContent).toContain("∞");
  } finally {
    await act(async () => root.unmount());
  }
});
