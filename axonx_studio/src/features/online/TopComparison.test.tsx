// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi, afterEach, beforeEach } from "vitest";
import i18n from "../../i18n";
import { getTaskStatus } from "../tasks/api";
import type { TaskMetadata } from "../tasks/types";
import { previewWorkspaceFile } from "../workspace/api";
import { TopComparison } from "./TopComparison";
import {
  parseTopComparison,
  topRows,
  type TopComparisonData,
  type TopStock,
} from "./topComparisonData";
vi.mock("../tasks/api", () => ({ getTaskStatus: vi.fn() }));
beforeEach(() =>
  vi
    .mocked(getTaskStatus)
    .mockResolvedValue({ started_at: "2026-01-11T00:00:00Z" } as TaskMetadata),
);
vi.mock("../workspace/api", () => ({ previewWorkspaceFile: vi.fn() }));
const stock = (code: string, rank: number, score = 1): TopStock => ({
  code,
  name: `Name ${code}`,
  rank,
  score,
  std: 0.1,
  seeds: { seed_0: score - 0.1, seed_1: score + 0.1 },
});
function fixture(): TopComparisonData {
  const on = Array.from({ length: 12 }, (_, i) => stock(`S${i}`, i + 1));
  const off = on.map((r) => ({
    ...r,
    rank: r.rank === 1 ? 12 : r.rank === 12 ? 1 : r.rank,
  }));
  const group = {
    online: { count: 12, rows: on },
    offline: { count: 12, rows: off },
  };
  return {
    version: 1,
    key: "20240102/1445",
    std_ddof: 0,
    absolute_tolerance: 1e-6,
    relative_tolerance: 1e-6,
    score_selection: { seed: null, aggregation: "mean" },
    universe: { kind: "all" },
    scopes: { buyable: group, all: structuredClone(group) },
  };
}
(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;
afterEach(() => vi.clearAllMocks());
it("aligns both Top N lists by code and retains ranks outside N", () => {
  const data = parseTopComparison(fixture());
  const rows = topRows(data, "buyable", 5);
  expect(rows).toHaveLength(6);
  expect(rows.find((r) => r.code === "S0")).toMatchObject({
    membership: "onlineOnly",
    offline: { rank: 12 },
  });
  expect(rows.at(-1)).toMatchObject({ code: "S11", membership: "offlineOnly" });
  expect(rows.filter((r) => r.membership === "both")).toHaveLength(4);
  const tiny = fixture();
  tiny.scopes.buyable.offline.rows[1].score += 1e-8;
  expect(
    topRows(tiny, "buyable", 5).find((r) => r.code === "S1")?.different,
  ).toBe(false);
});
it("rejects incomplete ranks and duplicate stocks rather than inventing overlap", () => {
  const bad = fixture();
  bad.scopes.buyable.online.rows.pop();
  expect(() => parseTopComparison(bad)).toThrow();
  const duplicate = fixture();
  duplicate.scopes.all.online.rows[1].code = "S0";
  expect(() => parseTopComparison(duplicate)).toThrow();
});
it.each(["en", "zh"])(
  "loads the selected machine artifact and switches N and differences in %s",
  async (language) => {
    await i18n.changeLanguage(language);
    vi.mocked(previewWorkspaceFile).mockResolvedValue({
      kind: "json",
      data: fixture(),
      truncated: false,
    } as Awaited<ReturnType<typeof previewWorkspaceFile>>);
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);
    const artifact = {
      path: "top_comparisons/20240102_1445.json",
      size: 1000,
      revision: "1:1",
    };
    try {
      await act(async () =>
        root.render(
          <TopComparison
            taskId="analysis#compare#test"
            startedAt="2026-01-11T00:00:00Z"
            artifact={artifact}
            target="selected-machine"
            windowKey="20240102/1445"
          />,
        ),
      );
      expect(vi.mocked(previewWorkspaceFile).mock.calls[0][3]).toBe(
        "selected-machine",
      );
      const headers = [...container.querySelectorAll("thead th")].map(
        (cell) => cell.textContent,
      );
      expect(headers).toContain(i18n.t("topComparison.code"));
      expect(headers).toContain(i18n.t("topComparison.name"));
      expect(container.querySelectorAll("select")).toHaveLength(0);
      expect(
        container.querySelectorAll('.online-table-tools [role="combobox"]'),
      ).toHaveLength(2);
      expect(
        container.querySelectorAll(".top-comparison-summary"),
      ).toHaveLength(1);
      const topN = container.querySelector<HTMLButtonElement>(
        `[role="combobox"][aria-label="${i18n.t("topComparison.topN")}"]`,
      )!;
      await act(async () => topN.click());
      await act(async () =>
        [...document.querySelectorAll<HTMLButtonElement>('[role="option"]')]
          .find((option) => option.textContent?.includes("Top 5"))!
          .click(),
      );
      expect(container.textContent).toContain(
        i18n.t("topComparison.overlap", { count: 4, n: 5 }),
      );
      expect(container.querySelectorAll("tbody > tr")).toHaveLength(6);
      const filter = container.querySelector<HTMLInputElement>(
        'input[type="checkbox"]',
      )!;
      await act(async () => filter.click());
      expect(container.querySelectorAll("tbody > tr")).toHaveLength(2);
      expect(container.textContent).toContain("1 / 12");
      expect(container.querySelector("pre")).toBeNull();
    } finally {
      await act(async () => root.unmount());
      container.remove();
    }
  },
);

it("keeps the non-buyable counterpart score without adding it to Top N", () => {
  const data = fixture();
  data.scopes.buyable.offline.rows[0].rank = null;
  data.scopes.buyable.offline.count = 11;
  const row = topRows(parseTopComparison(data), "buyable", 5).find(
    (r) => r.code === "S0",
  );
  expect(row).toMatchObject({
    membership: "onlineOnly",
    offline: { rank: null, score: 1 },
  });
});

it.each([true, false])(
  "refuses a comparison owner replaced before/during reading (before=%s)",
  async (before) => {
    vi.mocked(getTaskStatus).mockReset();
    if (!before)
      vi.mocked(getTaskStatus).mockResolvedValueOnce({
        started_at: "2026-01-11T00:00:00Z",
      } as TaskMetadata);
    vi.mocked(getTaskStatus).mockResolvedValue({
      started_at: "2026-01-12T00:00:00Z",
    } as TaskMetadata);
    vi.mocked(previewWorkspaceFile).mockResolvedValue({
      kind: "json",
      data: fixture(),
      truncated: false,
    } as Awaited<ReturnType<typeof previewWorkspaceFile>>);
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);
    try {
      await act(async () =>
        root.render(
          <TopComparison
            taskId="analysis#compare#test"
            startedAt="2026-01-11T00:00:00Z"
            windowKey="20240102/1445"
            artifact={{ path: "top.json", size: 100, revision: "1:1" }}
          />,
        ),
      );
      expect(container.querySelector('[role="alert"]')?.textContent).toContain(
        i18n.t("onlinePipeline.replacedChild"),
      );
      expect(container.querySelector("table")).toBeNull();
      expect(vi.mocked(previewWorkspaceFile).mock.calls).toHaveLength(
        before ? 0 : 1,
      );
    } finally {
      await act(async () => root.unmount());
      container.remove();
    }
  },
);
