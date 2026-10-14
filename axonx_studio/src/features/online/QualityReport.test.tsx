// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { QualityReport, TaskQuality } from "./QualityReport";
import { parseQuality } from "./quality";
import { loadArtifactRows } from "./api";
import { parseOnlineReport } from "./types";

vi.mock("./api", () => ({ loadArtifactRows: vi.fn() }));
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
  sha256: "a".repeat(64),
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
    expect(container.textContent).toContain("80.00%");
    expect(container.textContent).toContain(i18n.t("quality.actions.warning"));
    expect(container.textContent).not.toContain(
      i18n.t("quality.reasons.missing_name"),
    );
    await act(async () =>
      container
        .querySelector<HTMLInputElement>('input[type="checkbox"]')!
        .click(),
    );
    expect(container.textContent).toContain(
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
    "remote",
    expect.any(AbortSignal),
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
