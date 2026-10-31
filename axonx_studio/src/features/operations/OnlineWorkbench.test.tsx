// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { seed } from "../../playground/fixtures";
import { createPlayground } from "../../playground/runtime";
import { AxonXClient, configureClient } from "../../shared/api/client";
import type { TaskMetadata } from "../../shared/api/contracts";
import type { ReportNode } from "./daily";
import { OnlineWorkbench } from "./OnlineWorkbench";
import { parseStockReport } from "./report";

let root: Root;
let container: HTMLDivElement;
let parent: TaskMetadata;
let nodes: ReportNode[];
const clickTab = async (key: string) =>
  act(async () =>
    container
      .querySelector<HTMLButtonElement>(`[role="tab"][id$="-${key}-tab"]`)!
      .click(),
  );
const panel = () =>
  container.querySelector<HTMLElement>(
    '.online-scope-content > .operation-tabs > [role="tabpanel"]:not([hidden])',
  )!;
const date = async (value: string) =>
  act(async () => {
    const input =
      container.querySelector<HTMLInputElement>('input[type="date"]')!;
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!.call(input, value);
    input.dispatchEvent(new Event("change", { bubbles: true }));
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
const render = async (error = "", target?: string) =>
  act(async () =>
    root.render(
      <OnlineWorkbench
        parent={parent}
        nodes={nodes}
        refreshedAt="2026-01-05T06:46:00Z"
        error={error}
        target={target}
        onOpenTask={vi.fn()}
      />,
    ),
  );
beforeEach(async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  await i18n.changeLanguage("zh");
  const tasks = seed().tasks;
  parent = structuredClone(tasks.get("base#playground_online#demo")!);
  const child = structuredClone(tasks.get("inference#playground_online#demo")!);
  nodes = [
    {
      record: parent.children[0],
      status: child,
      error: "",
      report: parseStockReport(child.output_params.report),
    },
  ];
  configureClient(new AxonXClient(createPlayground(), false));
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  configureClient(new AxonXClient());
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const selectModel = async (value: string) => {
  await act(async () => {
    container.querySelector<HTMLButtonElement>(".online-model-picker")!.click();
  });
  await act(async () => {
    [...document.querySelectorAll<HTMLButtonElement>('[role="option"]')]
      .find((option) => option.textContent === value)!
      .click();
  });
};

it("uses exactly two navigation rows, labels time status and opens result views without more tabs", async () => {
  await render();
  expect(container.querySelectorAll('[role="tablist"]')).toHaveLength(2);
  expect(container.querySelectorAll('input[type="date"]')).toHaveLength(1);
  expect(
    container.querySelector(".online-time-navigation")?.textContent,
  ).toContain("14:45");
  expect(panel().textContent).toContain(
    i18n.t("onlinePipeline.phases.snapshot"),
  );
  await clickTab("1445");
  await clickTab("results");
  expect(panel().textContent).toContain("Synthetic 1");
  expect(container.querySelectorAll('[role="tablist"]')).toHaveLength(2);
  expect(container.querySelector(".backtest-tabs")).toBeNull();
  expect(container.querySelector("details")).toBeNull();
});

it("groups before and bar under one time and keeps the opening snapshot only under Data", async () => {
  const snapshot = parent.steps.find((step) => step.group === "collection")!;
  parent.steps.push(
    {
      ...snapshot,
      name: "collection:0945_before",
      label: "0945_before",
      state: "done",
    },
    {
      ...snapshot,
      name: "collection:0945_bar",
      label: "0945_bar",
      state: "running",
    },
  );
  await render();
  expect(
    container.querySelectorAll('.online-time-navigation [role="tab"]'),
  ).toHaveLength(3);
  expect(panel().textContent).not.toContain("0945_bar");
  await clickTab("0945");
  expect(panel().textContent).toContain("0945_before");
  expect(panel().textContent).toContain("0945_bar");
  expect(panel().textContent).not.toContain(
    i18n.t("onlinePipeline.phases.snapshot"),
  );
  expect(container.querySelector('[id$="-0945-tab"]')?.textContent).toContain(
    i18n.t("onlineWorkbench.states.running"),
  );
});

it("shows a shared ETL tab only for independent preparation and preserves history failures", async () => {
  await render();
  expect(container.querySelector('[id$="-etl-tab"]')).toBeNull();
  const template = parent.steps[0];
  parent.steps.push(
    {
      ...template,
      group: "etl",
      name: "etl:shared",
      label: "shared ETL",
      state: "done",
    },
    {
      ...template,
      group: "history",
      name: "history:demo-1445",
      state: "failed",
      error: "History unavailable",
    },
  );
  await render();
  await clickTab("etl");
  expect(panel().textContent).toContain("shared ETL");
  expect(container.querySelector('[id$="-preparation-tab"]')).toBeNull();
  await clickTab("1445");
  await clickTab("preparation");
  expect(panel().textContent).toContain("History unavailable");
  expect(container.querySelector('[id$="-1445-tab"]')?.textContent).toContain(
    i18n.t("onlineWorkbench.states.failed"),
  );
  expect(container.querySelector('[id$="-data-tab"]')?.textContent).toContain(
    i18n.t("onlineWorkbench.states.done"),
  );
  expect(container.querySelector("details")).toBeNull();
});

it("retains the chosen model name and stage when changing times and refreshing", async () => {
  parent.input_params.models = {
    "1000": [{ task_name: "demo" }, { task_name: "other" }],
    "1445": [{ task_name: "demo" }, { task_name: "other" }],
  };
  await render();
  await clickTab("1445");
  await clickTab("results");
  await selectModel("other");
  await clickTab("1000");
  await render("refresh failed");
  expect(
    container.querySelector(".online-model-picker strong")!.textContent,
  ).toBe("other");
  expect(
    container
      .querySelector('[id$="-results-tab"]')
      ?.getAttribute("aria-selected"),
  ).toBe("true");
  expect(
    container.querySelector('[id$="-1000-tab"]')?.getAttribute("aria-selected"),
  ).toBe("true");
  expect(container.textContent).toContain("refresh failed");
});

it("keeps a failed model separate from another model's valid signal at the same time", async () => {
  parent.input_params.models = {
    "1445": [{ task_name: "demo" }, { task_name: "other" }],
  };
  parent.output_params.models = {
    "1445": {
      other: { status: "failed", error: "data_not_ready_before_deadline" },
    },
  };
  await render();
  expect(container.querySelector('[id$="-1445-tab"]')?.textContent).toContain(
    i18n.t("onlineWorkbench.states.failed"),
  );
  await clickTab("1445");
  await clickTab("results");
  expect(panel().textContent).toContain("Synthetic 1");
  await selectModel("other");
  expect(panel().textContent).not.toContain(i18n.t("onlineWorkbench.noSignal"));
  expect(panel().textContent).not.toContain("Synthetic 1");
  await clickTab("results");
  expect(panel().textContent).toContain(
    i18n.t("onlinePipeline.reasons.data_not_ready_before_deadline"),
  );
});

it.each(["en", "zh"])(
  "waits quietly for the first signal and loads it on refresh in %s",
  async (language) => {
    await i18n.changeLanguage(language);
    vi.useFakeTimers();
    const playground = createPlayground();
    let unpublished = true;
    parent.output_params.models = {};
    nodes[0].report = null;
    parent.children[0].state = "running";
    nodes[0].status!.state = "running";
    nodes[0].status!.steps = [];
    configureClient(
      new AxonXClient(async (url, init) => {
        if (
          url === "/jobs/preview_file" &&
          String(init?.body).includes("metadata.json") &&
          unpublished
        ) {
          expect(JSON.parse(String(init?.body)).arguments.allow_missing).toBe(
            true,
          );
          return Response.json({ success: true, answer: null });
        }
        return playground(url, init);
      }, false),
    );
    await render();
    await clickTab("1445");
    await clickTab("results");
    expect(container.querySelector(".online-warning")).toBeNull();
    expect(panel().textContent).toContain(i18n.t("onlineWorkbench.noSignal"));
    unpublished = false;
    await act(async () => vi.advanceTimersByTimeAsync(60_000));
    expect(panel().textContent).toContain("Synthetic 1");
    // A previously read history disappearing is a real error; retain its last valid signals.
    configureClient(
      new AxonXClient(async (url, init) => {
        if (
          url === "/jobs/preview_file" &&
          String(init?.body).includes("metadata.json")
        ) {
          expect(
            JSON.parse(String(init?.body)).arguments.allow_missing,
          ).toBeUndefined();
          return Response.json({
            success: false,
            answer: "Workspace file does not exist",
          });
        }
        return playground(url, init);
      }, false),
    );
    await act(async () => vi.advanceTimersByTimeAsync(60_000));
    expect(container.textContent).toContain(
      i18n.t("onlineWorkbench.historyError"),
    );
    expect(panel().textContent).toContain("Synthetic 1");
  },
);

it("keeps missing published daily metadata visible as an error", async () => {
  const playground = createPlayground();
  configureClient(
    new AxonXClient(async (url, init) => {
      if (
        url === "/jobs/preview_file" &&
        String(init?.body).includes("metadata.json")
      ) {
        expect(
          JSON.parse(String(init?.body)).arguments.allow_missing,
        ).toBeUndefined();
        return Response.json({
          success: false,
          answer: "Workspace file does not exist",
        });
      }
      return playground(url, init);
    }, false),
  );
  await render();
  expect(container.textContent).toContain(
    i18n.t("onlineWorkbench.historyError"),
  );
});

it("shows active stages and each failure once without a redundant no-signal message", async () => {
  nodes[0].report = null;
  const playground = createPlayground();
  configureClient(
    new AxonXClient(async (url, init) => {
      if (
        url === "/jobs/preview_file" &&
        String(init?.body).includes("metadata.json")
      )
        return Response.json({ success: true, answer: null });
      return playground(url, init);
    }, false),
  );
  nodes[0].status!.steps = [
    {
      ...parent.steps[0],
      name: "waiting_inputs",
      label: "waiting_inputs",
      parent: "run_windows",
      group: "inference",
      state: "running",
      error: "",
    },
  ];
  await render();
  await clickTab("1445");
  await clickTab("results");
  expect(panel().textContent).toContain(
    i18n.t("onlinePipeline.phases.waiting_inputs"),
  );
  expect(panel().textContent).not.toContain(i18n.t("onlineWorkbench.noSignal"));
  const error = "Prediction deadline exceeded";
  parent.children[0].error = error;
  nodes[0].status!.steps[0].state = "failed";
  nodes[0].status!.steps[0].error = error;
  await render();
  expect(panel().textContent!.split(error)).toHaveLength(2);
  expect(panel().textContent).not.toContain(i18n.t("onlineWorkbench.noSignal"));
});

it("shows only the signal table in daily results without nested result views", async () => {
  await render();
  await clickTab("1445");
  await clickTab("results");
  expect(panel().textContent).toContain("Synthetic 1");
  expect(
    panel().querySelector(
      `[aria-label="${i18n.t("onlineWorkbench.resultView")}"]`,
    ),
  ).toBeNull();
  expect(
    panel().querySelector(`[aria-label="${i18n.t("backtest.universe")}"]`),
  ).not.toBeNull();
  expect(panel().querySelectorAll(".online-revision")).toHaveLength(0);
});

it("never substitutes current signals, stages or logs for an empty historical date", async () => {
  await render();
  await clickTab("1445");
  await clickTab("results");
  expect(panel().textContent).toContain("Synthetic 1");
  await date("2020-01-01");
  expect(panel().textContent).toContain(i18n.t("onlineWorkbench.noSignal"));
  expect(panel().textContent).not.toContain("Synthetic 1");
  expect(panel().textContent).not.toContain(
    i18n.t("onlineWorkbench.noTaskRecord"),
  );
  await clickTab("logs");
  expect(panel().textContent).toContain(i18n.t("onlineWorkbench.noTaskRecord"));
  expect(panel().querySelector(".log-content")).toBeNull();
  await clickTab("preparation");
  expect(panel().textContent).toContain(i18n.t("onlineWorkbench.noTaskRecord"));
});

it("keeps a daily archive readable after its child is replaced and metadata refresh fails", async () => {
  vi.useFakeTimers();
  parent.children = [];
  nodes = [];
  await render();
  await clickTab("1445");
  await clickTab("results");
  expect(panel().textContent).toContain("Synthetic 1");
  const playground = createPlayground();
  configureClient(
    new AxonXClient(async (url, init) => {
      if (
        url === "/jobs/preview_file" &&
        String(init?.body).includes("metadata.json")
      )
        return new Response("unavailable", { status: 503 });
      return playground(url, init);
    }, false),
  );
  await act(async () => vi.advanceTimersByTimeAsync(60_000));
  expect(container.textContent).toContain(
    i18n.t("onlineWorkbench.historyError"),
  );
  expect(panel().textContent).toContain("Synthetic 1");
});

it("loads the daily parent archive without discovering current inference children", async () => {
  const playground = createPlayground();
  configureClient(
    new AxonXClient(async (url, init) => {
      expect(url).not.toBe("/jobs/list_task_statuses");
      return playground(url, init);
    }, false),
  );
  parent.children = [];
  nodes = [];
  await render();
  expect(container.querySelectorAll("datalist option")).toHaveLength(12);
  await clickTab("1445");
  await clickTab("results");
  expect(panel().textContent).toContain("Synthetic 1");
  await date("2020-01-01");
  expect(panel().textContent).toContain(i18n.t("onlineWorkbench.noSignal"));
  expect(panel().textContent).not.toContain("Synthetic 1");
});

it("keeps archived models separate when another planned model has no result", async () => {
  parent.children = [];
  nodes = [];
  parent.input_params.models = {
    "1445": [{ task_name: "demo" }, { task_name: "other" }],
  };
  await render();
  await clickTab("1445");
  await clickTab("results");
  expect(panel().textContent).toContain("Synthetic 1");
  await selectModel("other");
  expect(panel().textContent).toContain(i18n.t("onlineWorkbench.noSignal"));
  expect(panel().textContent).not.toContain("Synthetic 1");
});

it("does not substitute a current worker for a missing daily archived result", async () => {
  parent.children = [];
  parent.output_params.models = {};
  nodes = [];
  await render();
  await clickTab("1445");
  await clickTab("results");
  expect(panel().textContent).toContain(i18n.t("onlineWorkbench.noSignal"));
  expect(panel().textContent).not.toContain("Synthetic 1");
});

it("keeps quality sources within the selected scope and displays checks directly", async () => {
  const quality = (reason: string) => ({
    version: 1,
    trade_date: "20260105",
    trade_time: "1445",
    checks: [
      {
        stage: "snapshot",
        reason,
        action: "warning",
        input_count: 10,
        output_count: 10,
        matched_count: 1,
        removed_count: 0,
        samples: [],
      },
    ],
  });
  parent.output_params.windows = [
    {
      key: "snapshot",
      status: "done",
      metrics: { quality: quality("shared-check") },
    },
    {
      key: "1445_bar",
      status: "done",
      metrics: { quality: quality("selected-slot-check") },
    },
    {
      key: "1000_bar",
      status: "done",
      metrics: { quality: quality("other-slot-check") },
    },
    {
      key: "1445_before",
      status: "done",
      metrics: { quality: quality("before-slot-check") },
    },
  ];
  await render();
  await clickTab("quality-snapshot");
  expect(panel().textContent).toContain("shared-check");
  expect(panel().textContent).not.toContain("selected-slot-check");
  await clickTab("1445");
  await clickTab("quality-before");
  expect(panel().textContent).toContain("before-slot-check");
  expect(panel().textContent).not.toContain("selected-slot-check");
  await clickTab("quality-bar");
  expect(panel().textContent).toContain("selected-slot-check");
  expect(panel().textContent).not.toContain("before-slot-check");
  expect(panel().textContent).not.toContain("shared-check");
  expect(panel().textContent).not.toContain("other-slot-check");
  expect(panel().querySelectorAll("table")).toHaveLength(1);
  await clickTab("quality-model");
  expect(panel().querySelectorAll("table")).toHaveLength(1);
  expect(panel().querySelector(".quality-inline-details")).not.toBeNull();
  expect(panel().querySelector("select")).toBeNull();
  expect(container.querySelectorAll('[role="tablist"]')).toHaveLength(2);
  expect(container.querySelector('[role="dialog"]')).toBeNull();
  expect(container.querySelector('[id$="-checks-tab"]')).toBeNull();
  expect(container.querySelector('[id$="-samples-tab"]')).toBeNull();
  expect(container.querySelector('[id$="-details-tab"]')).toBeNull();
});

it("places failure next to the task name and hides only the generic exit message", async () => {
  parent.state = "failed";
  parent.error = "Task exited with code 1";
  await render();
  expect(container.querySelector(".online-task-title")?.textContent).toContain(
    i18n.t("states.failed"),
  );
  expect(container.textContent).not.toContain(parent.error);
  parent.error = "History source is unavailable";
  await render();
  expect(container.querySelector('[role="alert"]')?.textContent).toContain(
    parent.error,
  );
  await render("refresh failed");
  expect(container.querySelector('[role="alert"]')?.textContent).toContain(
    "refresh failed",
  );
});

it("opens the model menu below the control and supports keyboard selection and dismissal", async () => {
  parent.input_params.models = {
    "1445": [{ task_name: "demo" }, { task_name: "other" }],
  };
  await render();
  await clickTab("1445");
  const trigger = () =>
    container.querySelector<HTMLButtonElement>('[role="combobox"]')!;
  const key = (key: string) =>
    act(async () =>
      trigger().dispatchEvent(
        new KeyboardEvent("keydown", { key, bubbles: true }),
      ),
    );
  await key("ArrowDown");
  expect(trigger().getAttribute("aria-expanded")).toBe("true");
  expect(document.querySelector('[role="listbox"]')?.id).toBe(
    trigger().getAttribute("aria-controls"),
  );
  await key("ArrowDown");
  await key("Enter");
  expect(trigger().textContent).toContain("other");
  expect(document.querySelector('[role="listbox"]')).toBeNull();
  await act(async () => trigger().click());
  await key("Escape");
  expect(trigger().getAttribute("aria-expanded")).toBe("false");
  await act(async () => trigger().click());
  await act(async () =>
    document.body.dispatchEvent(new Event("pointerdown", { bubbles: true })),
  );
  expect(document.querySelector('[role="listbox"]')).toBeNull();
});

it("consolidates the slot navigation and removes completed status-only prediction cards", async () => {
  await render();
  await clickTab("1445");
  expect(
    [...container.querySelectorAll('.online-scope-content [role="tab"]')].map(
      (tab) => tab.textContent,
    ),
  ).toEqual([
    i18n.t("onlinePipeline.collection"),
    i18n.t("onlineWorkbench.modelPreparation"),
    i18n.t("onlineWorkbench.predictionResults"),
    i18n.t("onlineWorkbench.qualitySources.before"),
    i18n.t("onlineWorkbench.qualitySources.bar"),
    i18n.t("onlineWorkbench.qualitySources.model"),
    i18n.t("taskDetail.logs"),
  ]);
  nodes[0].status!.steps = nodes[0].status!.steps.map((step) => ({
    ...step,
    phase: "done",
    completed: 1,
    total: 1,
  }));
  await render();
  await clickTab("results");
  expect(panel().textContent).toContain("Synthetic 1");
  expect(panel().querySelector(".online-metrics")).toBeNull();
  expect(panel().querySelector(".online-signal-toolbar")).not.toBeNull();
  expect(panel().querySelector(".online-summary")).toBeNull();
  expect(panel().querySelector(".pipeline-model-content")).toBeNull();
  expect(panel().querySelector(".online-stage-heading")).toBeNull();
  expect(container.querySelector('[id$="-scoring-tab"]')).toBeNull();
  expect(container.querySelector('[id$="-provenance-tab"]')).toBeNull();
  // A failed prediction remains useful even without metrics or files.
  nodes[0].status!.steps = nodes[0].status!.steps.map((step) =>
    step.name === "prediction"
      ? { ...step, state: "failed", error: "Predictor unavailable" }
      : step,
  );
  await render();
  expect(panel().textContent).toContain("Predictor unavailable");
});

it("shows only the selected inference log even when nested tasks share its name", async () => {
  const inference = nodes[0];
  const child = structuredClone(inference.status!);
  child.task_id = "api#log-source#demo";
  child.started_at = "2026-01-03T00:00:00Z";
  child.task_type = "api";
  child.reg_name = "prepare";
  child.input_params.task_name = inference.status!.input_params.task_name;
  const record = {
    ...inference.record,
    child_task_id: child.task_id,
    started_at: child.started_at,
    reg_name: child.reg_name,
    node_name: "prepare",
  };
  inference.status!.children.push(record);
  nodes.push({ record, status: child, error: "" });
  await render();
  await clickTab("1445");
  await clickTab("logs");
  const toolbar = panel().querySelector(".log-panel .pipeline-log-controls")!;
  expect(toolbar.querySelector("select")).toBeNull();
  expect(toolbar.textContent).toContain(i18n.t("taskGraph.kinds.inference"));
  expect(toolbar.textContent).not.toContain("API");
  expect(toolbar.textContent).toContain(i18n.t("taskDetail.follow"));
  expect(toolbar.textContent).toContain(i18n.t("taskDetail.copy"));
  expect(
    toolbar.querySelector(".daily-log-caption")?.getAttribute("title"),
  ).toBe(inference.status!.task_id);
});

it.each(["zh", "en"])(
  "distinguishes advance preparation from collection and prediction in %s",
  async (language) => {
    await i18n.changeLanguage(language);
    parent.state = "running";
    parent.children = [];
    nodes = [];
    parent.input_params.models = {
      "0945": [{ task_name: "default-0945" }],
      "1000": [{ task_name: "default-1000" }],
    };
    const template = parent.steps[0];
    const slot = () => container.querySelector('[id$="-1000-tab"]')!;
    for (const [history, collection, prediction, expected] of [
      ["waiting", "waiting", "pending", "pending"],
      ["running", "waiting", "pending", "preparing"],
      ["done", "waiting", "pending", "ready"],
      ["skipped", "waiting", "pending", "pending"],
      ["running", "running", "pending", "running"],
      ["running", "done", "running", "running"],
      ["failed", "running", "pending", "failed"],
      ["running", "missed", "pending", "failed"],
      ["failed", "missed", "missed", "missed"],
    ] as const) {
      parent.steps = [
        {
          ...template,
          name: "history:default-1000-1000",
          group: "history",
          state: history,
        },
        {
          ...template,
          name: "collection:1000_before",
          group: "collection",
          state: collection,
        },
      ];
      parent.output_params.models = {
        "1000": { "default-1000": { status: prediction } },
      };
      await render();
      expect(slot().querySelector(`.status-${expected}`)?.textContent).toBe(
        i18n.t(`onlineWorkbench.states.${expected}`),
      );
      if (["pending", "preparing", "ready"].includes(expected))
        expect(
          slot().querySelector(`.status-${expected}`)?.getAttribute("title"),
        ).toBe(i18n.t(`onlineWorkbench.stateHints.${expected}`));
      expect(
        container.querySelector('[id$="-0945-tab"] .status-pending'),
      ).not.toBeNull();
    }
  },
);

it.each(["zh", "en"])(
  "requires completed history for every planned model before showing readiness in %s",
  async (language) => {
    await i18n.changeLanguage(language);
    parent.state = "running";
    parent.children = [];
    nodes = [];
    parent.input_params.models = {
      "1000": [{ task_name: "first" }, { task_name: "second" }],
    };
    const template = parent.steps[0];
    parent.steps = [
      {
        ...template,
        name: "history:first-1000",
        group: "history",
        state: "done",
      },
    ];
    const state = () =>
      container.querySelector('[id$="-1000-tab"] .online-status')!;
    await render();
    expect(state().textContent).toBe(i18n.t("onlineWorkbench.states.pending"));
    parent.steps.push({
      ...template,
      name: "history:unrelated-1000",
      group: "history",
      state: "done",
    });
    await render();
    expect(state().textContent).toBe(i18n.t("onlineWorkbench.states.pending"));
    parent.steps.push({
      ...template,
      name: "history:second-1000",
      group: "history",
      state: "done",
    });
    await render();
    expect(state().textContent).toBe(i18n.t("onlineWorkbench.states.ready"));
    parent.output_params.models = {
      "1000": {
        first: { status: "pending" },
        second: { status: "pending" },
      },
    };
    for (const terminal of ["succeeded", "failed"] as const) {
      parent.state = terminal;
      await render();
      expect(state().textContent).toBe(
        i18n.t("onlineWorkbench.states.incomplete"),
      );
    }
  },
);
