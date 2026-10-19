// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { OperationResult } from "./OperationResult";

let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});
const show = async (value: unknown) =>
  act(async () => root.render(<OperationResult value={value} />));

it.each(["zh", "en"])(
  "separates completed transfers from deferred and rejected items in %s",
  async (language) => {
    await i18n.changeLanguage(language);
    await show({
      uploaded: ["task-a"],
      deferred: ["task-b"],
      rejected: [],
      oversized: [],
      archives: 1,
    });
    expect(container.querySelector('[role="status"]')?.textContent).toBe(
      i18n.t("operations.incompleteResult"),
    );
    expect(container.querySelectorAll(".operation-metrics > div")).toHaveLength(
      5,
    );
    expect(container.querySelectorAll("details[open]")).toHaveLength(0);
    expect(container.querySelectorAll("details")).toHaveLength(3);
    expect(container.querySelector("pre")?.closest("details")?.open).toBe(
      false,
    );
    expect(container.textContent).toContain(
      i18n.t("operations.metrics.deferred"),
    );
  },
);

it("distinguishes missing results from a completed empty sync round", async () => {
  await show(null);
  expect(container.textContent).toBe(i18n.t("operations.noResult"));
  await show({
    uploaded: [],
    deferred: [],
    rejected: [],
    oversized: [],
    archives: 0,
  });
  expect(container.textContent).toContain(i18n.t("operations.nothingToSync"));
  expect(container.querySelector('[role="status"]')).toBeNull();
  expect(container.querySelectorAll("details")).toHaveLength(1);
});

it("retains data update totals, date range and partial failures", async () => {
  await show({
    status: "partial",
    start_date: "20261016",
    end_date: "20261019",
    attempted_count: 10,
    created_count: 3,
    changed_count: 2,
    unchanged_count: 4,
    rejected_count: 1,
    empty_count: 0,
  });
  expect(container.querySelector('[role="status"]')).not.toBeNull();
  expect(container.querySelector(".operation-facts")?.textContent).toContain(
    "20261019",
  );
  expect(container.querySelectorAll(".operation-metrics > div")).toHaveLength(
    6,
  );
  await show({ status: "done", attempted_count: 10, rejected_count: 0 });
  expect(container.querySelector('[role="status"]')).toBeNull();
});
