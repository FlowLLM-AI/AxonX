import { axonx } from "../../shared/api/client";
// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { seed } from "../../playground/fixtures";
import { listTaskDirectories, previewWorkspaceFile } from "../workspace/api";
import ResearchPage from "./ResearchPage";

vi.mock("../../shared/api/client", () => ({ axonx: { invoke: vi.fn() } }));
vi.mock("../workspace/api", () => ({
  listTaskDirectories: vi.fn(),
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
        ? tasks.get("backtest#demo")!
        : [tasks.get("backtest#demo")!],
    );
    const path = "backtest/backtest#demo";
    vi.mocked(listTaskDirectories).mockResolvedValue({
      path: "backtest",
      workspace_root: null,
      truncated: false,
      entries: [
        {
          name: "demo",
          path,
          kind: "directory",
          preview_kind: null,
          supported: true,
          size: null,
          modified_at: 0,
        },
      ],
    });
    vi.mocked(previewWorkspaceFile).mockImplementation(async (key) => {
      const preview = files.get(key);
      if (!preview) throw new Error(`Missing fixture ${key}`);
      return preview;
    });
    const container = document.createElement("div");
    const root = createRoot(container);
    try {
      await act(async () =>
        root.render(
          <ResearchPage
            kind="backtest"
            target="remote"
            initialSelectedId="backtest#demo"
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
          container.querySelector(".backtest-universe-selector select"),
        ).not.toBeNull();
      });
      const selector = container.querySelector<HTMLSelectElement>(
        ".backtest-universe-selector select",
      );
      expect(selector?.value).toBe("all");
      expect(container.querySelector(".base-files-card")).toBeNull();
      expect(container.querySelector(".artifact-kpis")).toBeNull();
      expect(container.textContent).not.toContain(
        i18n.t("backtest.unable_to_load_backtest_artifacts"),
      );
      expect(
        container.querySelector(".backtest-report-dates")?.textContent,
      ).toContain("60");
      await act(async () => {
        selector!.value = "hs300";
        selector!.dispatchEvent(new Event("change", { bubbles: true }));
      });
      expect(selector?.value).toBe("hs300");
      for (const universe of ["all", "hs300"]) {
        expect(previewWorkspaceFile).toHaveBeenCalledWith(
          `${path}/universes/${universe}/daily.parquet`,
          0,
          5000,
          "remote",
          expect.any(AbortSignal),
        );
      }
    } finally {
      await act(async () => root.unmount());
      container.remove();
    }
  },
);

it("reads training member count from the canonical model manifest", async () => {
  const { files, tasks } = seed();
  const task = tasks.get("train#demo")!;
  vi.mocked(axonx.invoke).mockImplementation(async (name) =>
    name === "status" ? task : [task],
  );
  vi.mocked(previewWorkspaceFile).mockImplementation(async (path) => {
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
          initialSelectedId="train#demo"
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
    expect(previewWorkspaceFile).toHaveBeenCalledWith(
      "train/train#demo/models.json",
      0,
      1,
      "remote",
      expect.any(AbortSignal),
    );
  } finally {
    await act(async () => root.unmount());
  }
});
