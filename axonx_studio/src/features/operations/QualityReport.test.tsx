// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { loadArtifactRows } from "../../shared/api/artifacts";
import { QualityReport, TaskQuality } from "./QualityReport";
import { parseOnlineReport, parseQuality } from "./report";

vi.mock("../../shared/api/artifacts", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../shared/api/artifacts")>()),
  loadArtifactRows: vi.fn(),
}));
const summary = parseQuality({
  version: 1,
  trade_date: "20240102",
  trade_time: "1445",
  checks: [
    {
      stage: "1445_bar",
      reason: "missing_slots",
      action: "warning",
      input_count: 100,
      output_count: 100,
      matched_count: 20,
      removed_count: 0,
      coverage: 0.8,
      threshold: 0.8,
      samples: [{ ts_code: "000001.SZ", missing_slots: "1445" }],
    },
    {
      stage: "reference",
      reason: "missing_name",
      action: "filter",
      input_count: 80,
      output_count: 80,
      matched_count: 0,
      removed_count: 0,
      samples: [],
    },
  ],
});
const artifact = {
  path: "diagnostics/1445/quality_details.parquet",
  revision: "1:1",
  size: 100,
};
let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  vi.clearAllMocks();
  (
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

it.each(["en", "zh"])(
  "shows warning counts, thresholds and optional checks in %s",
  async (language) => {
    await i18n.changeLanguage(language);
    await act(async () =>
      root.render(
        <QualityReport summary={summary} taskId="inference#test#demo" />,
      ),
    );
    expect(container.querySelectorAll('[role="tablist"]')).toHaveLength(0);
    await act(async () =>
      [...container.querySelectorAll<HTMLButtonElement>("button")]
        .find((button) => button.textContent === i18n.t("quality.checksTab"))!
        .click(),
    );
    expect(
      container.querySelector("button[aria-pressed]")?.textContent,
    ).toContain(i18n.t("quality.showAll"));
    expect(container.textContent).not.toContain("📋");
    expect(container.textContent).toContain("80.00%");
    expect(container.textContent).toContain(i18n.t("quality.actions.warning"));
    expect(container.textContent).not.toContain(
      i18n.t("quality.reasons.missing_name"),
    );
    await act(async () =>
      container
        .querySelector<HTMLButtonElement>("button[aria-pressed]")!
        .click(),
    );
    expect(container.textContent).toContain(
      i18n.t("quality.reasons.missing_name"),
    );
    expect(
      container.querySelector("button[aria-pressed]")?.textContent,
    ).toContain(i18n.t("quality.showRelevant"));
    await act(async () =>
      container
        .querySelector<HTMLButtonElement>("button[aria-pressed]")!
        .click(),
    );
    expect(container.textContent).not.toContain(
      i18n.t("quality.reasons.missing_name"),
    );
  },
);

it("loads details only on demand, preserves target, and shows request failures with retry", async () => {
  vi.mocked(loadArtifactRows)
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce([{ ts_code: "000001.SZ", details: "missing 1445" }]);
  await act(async () =>
    root.render(
      <QualityReport
        summary={summary}
        taskId="inference#test#demo"
        target="remote"
        artifacts={{ quality_details: artifact }}
      />,
    ),
  );
  expect(loadArtifactRows).not.toHaveBeenCalled();
  await act(async () =>
    [...container.querySelectorAll("button")]
      .find((b) => b.textContent === i18n.t("quality.details"))!
      .click(),
  );
  expect(container.querySelector('[role="alert"]')?.textContent).toContain(
    "offline",
  );
  await act(async () =>
    container
      .querySelector<HTMLButtonElement>('[role="alert"] button')!
      .click(),
  );
  expect(container.textContent).toContain("missing 1445");
  expect(loadArtifactRows).toHaveBeenLastCalledWith(
    "inference#test#demo",
    artifact,
    { target: "remote", signal: expect.any(AbortSignal) },
  );
});

it("keeps failed-window diagnostics visible and handles old and malformed records", async () => {
  await act(async () =>
    root.render(
      <TaskQuality
        taskId="inference#test#demo"
        windows={[
          {
            key: "1445",
            status: "failed",
            metrics: { quality: summary },
            artifacts: {},
          },
        ]}
      />,
    ),
  );
  expect(container.textContent).toContain(
    i18n.t("onlinePipeline.status.failed"),
  );
  expect(container.textContent).toContain("20240102");
  expect(
    parseOnlineReport({ windows: [{ key: "1445", status: "done" }] }).windows,
  ).toHaveLength(1);
  expect(() =>
    parseOnlineReport({
      windows: [
        {
          key: "1445",
          status: "failed",
          metrics: { quality: { ...summary, checks: [{}] } },
        },
      ],
    }),
  ).toThrow("Invalid quality summary");
  await act(async () =>
    root.render(
      <TaskQuality
        taskId="inference#test#demo"
        windows={[{ key: "1445", metrics: { quality: {} } }]}
      />,
    ),
  );
  expect(container.querySelector('[role="alert"]')?.textContent).toContain(
    "Invalid quality summary",
  );
});

it("renders a controlled quality page directly without a drawer or another navigation row", async () => {
  await act(async () =>
    root.render(
      <QualityReport
        summary={summary}
        taskId="inference#test#demo"
        view="checks"
      />,
    ),
  );
  expect(container.textContent).toContain("80.00%");
  expect(container.querySelector('[role="dialog"]')).toBeNull();
  expect(container.querySelector('[role="tablist"]')).toBeNull();
  expect(container.querySelector(".quality-summary-bar")).toBeNull();
});

it("omits the duplicate window heading when quality is a second-row page", async () => {
  await act(async () =>
    root.render(
      <TaskQuality
        taskId="inference#test#demo"
        view="checks"
        windows={[
          { key: "snapshot", status: "done", metrics: { quality: summary } },
        ]}
      />,
    ),
  );
  expect(container.querySelector(".online-quality-window > header")).toBeNull();
  expect(container.querySelector("table")).not.toBeNull();
});

it("loads complete details on demand and expands samples inline", async () => {
  await i18n.changeLanguage("zh");
  vi.mocked(loadArtifactRows).mockResolvedValue([
    {
      stage: "1445_bar",
      reason: "missing_slots",
      action: "warning",
      ts_code: "000002.SZ",
      details: "complete evidence",
    },
  ]);
  await act(async () =>
    root.render(
      <QualityReport
        summary={summary}
        taskId="inference#test#demo"
        target="machine-b"
        artifacts={{ quality_details: artifact }}
        view="overview"
      />,
    ),
  );
  expect(container.querySelectorAll("table")).toHaveLength(1);
  expect(loadArtifactRows).not.toHaveBeenCalled();
  const button = (label: string) =>
    [...container.querySelectorAll<HTMLButtonElement>("button")].find(
      (item) => item.textContent === label,
    )!;
  await act(async () =>
    button(i18n.t("quality.viewSamples", { count: 1 })).click(),
  );
  expect(container.querySelector('[role="dialog"]')).toBeNull();
  expect(
    container.querySelector(".online-expanded-row")?.textContent,
  ).toContain("000001.SZ");
  expect(container.querySelectorAll("table")).toHaveLength(1);
  expect(container.textContent).not.toContain("ℹ️");
  expect(loadArtifactRows).not.toHaveBeenCalled();
  await act(async () =>
    button(i18n.t("quality.viewSamples", { count: 1 })).click(),
  );
  expect(container.querySelector(".online-expanded-row")).toBeNull();
  await act(async () =>
    container.querySelector<HTMLElement>("details > summary")!.click(),
  );
  expect(loadArtifactRows).toHaveBeenCalledWith(
    "inference#test#demo",
    artifact,
    { target: "machine-b", signal: expect.any(AbortSignal) },
  );
  expect(container.querySelector('[role="dialog"]')).toBeNull();
  expect(
    container.querySelector(".quality-inline-details")?.textContent,
  ).toContain("000002.SZ");
  expect(container.querySelectorAll("table")).toHaveLength(2);
  expect(container.querySelector(".quality-inline-details")).not.toBeNull();
  expect(
    [...container.querySelectorAll("button")].some(
      (item) => item.textContent === i18n.t("onlineWorkbench.stockDetails"),
    ),
  ).toBe(false);
});

it.each(["en", "zh"])(
  "shows zero-issue checks as passed in current and historical reports in %s",
  async (language) => {
    await i18n.changeLanguage(language);
    for (const action of [
      "warning",
      "filter",
      "blocking",
      "unbuyable",
      "passed",
    ]) {
      const passed = {
        ...summary,
        checks: [
          {
            ...summary.checks[0],
            action,
            matched_count: 0,
            coverage: 1,
            samples: [],
          },
        ],
      };
      await act(async () =>
        root.render(
          <QualityReport summary={passed} taskId="demo" view="overview" />,
        ),
      );
      expect(container.textContent).toContain(i18n.t("quality.actions.passed"));
      expect(container.querySelector("tbody")?.textContent).not.toContain(
        i18n.t("quality.actions.warning"),
      );
      expect(container.textContent).toContain("100.00%");
      expect(container.textContent).toContain("80.00%");
    }
  },
);

it.each(["en", "zh"])(
  "does not call an empty check passed in %s",
  async (language) => {
    await i18n.changeLanguage(language);
    const empty = {
      ...summary,
      checks: [
        {
          ...summary.checks[0],
          input_count: 0,
          output_count: 0,
          matched_count: 0,
          coverage: 0,
          samples: [],
        },
      ],
    };
    await act(async () =>
      root.render(
        <QualityReport summary={empty} taskId="demo" view="overview" />,
      ),
    );
    expect(container.textContent).toContain(
      i18n.t("quality.noDataCount", { count: 1 }),
    );
    expect(container.querySelector("tbody")).toBeNull();
  },
);

it.each(["en", "zh"])(
  "keeps compact results and separates issues from actions in %s",
  async (language) => {
    await i18n.changeLanguage(language);
    await act(async () =>
      root.render(
        <QualityReport summary={summary} taskId="demo" view="overview" />,
      ),
    );
    expect(container.querySelectorAll("thead th")).toHaveLength(4);
    expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
    const rows = container.querySelectorAll("tbody tr");
    expect(rows[0].querySelector(".online-status")?.textContent).toBe(
      i18n.t("quality.actions.warning"),
    );
    expect(rows[1].querySelector(".online-status")?.textContent).toBe(
      i18n.t("quality.actions.passed"),
    );
    expect(rows[0].textContent).toContain("80.00%");
    expect(container.querySelector("button[aria-pressed]")).toBeNull();
  },
);
