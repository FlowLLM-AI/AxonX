// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { taskStatus } from "../../playground/fixtures";
import { ExecutionSteps } from "./ExecutionSteps";

it("uses lifecycle state rather than percentage to identify completion", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  const task = taskStatus("base", "base#demo#progress", "progress");
  const step = task.steps[0];
  task.steps = [
    {
      ...step,
      name: "execute",
      state: "running",
      percentage: 100,
      finished_at: null,
    },
    {
      ...step,
      name: "waiting",
      state: "waiting",
      percentage: null,
      finished_at: null,
    },
    { ...step, name: "skipped", state: "skipped", percentage: 100 },
    { ...step, name: "done", state: "done", percentage: 70 },
  ];
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    await act(async () => root.render(<ExecutionSteps task={task} />));
    expect(container.querySelectorAll(".active")).toHaveLength(1);
    expect(container.querySelectorAll(".done")).toHaveLength(1);
    expect(
      container.querySelectorAll(".step-item")[0].querySelector(".active"),
    ).not.toBeNull();
    expect(
      container.querySelectorAll(".step-item")[3].querySelector(".done"),
    ).not.toBeNull();
  } finally {
    await act(async () => root.unmount());
    vi.unstubAllGlobals();
  }
});

it.each(["running", "failed"] as const)(
  "folds consecutive completed repetitions while keeping the %s step visible",
  async (state) => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    await i18n.changeLanguage(state === "running" ? "zh" : "en");
    const task = taskStatus("api", "api#demo", "demo");
    task.state = state;
    task.error = state === "failed" ? "download failed" : "";
    const step = task.steps[0];
    task.steps = [
      { ...step, name: "initialize" },
      ...Array.from({ length: 1000 }, () => ({ ...step, name: "partial" })),
      { ...step, name: "checkpoint" },
      { ...step, name: "partial" },
      { ...step, name: "partial" },
      { ...step, name: "partial", percentage: 20, finished_at: null, state },
    ];
    const container = document.createElement("div");
    const root = createRoot(container);
    try {
      await act(async () => root.render(<ExecutionSteps task={task} />));
      expect(container.querySelectorAll(".step-item")).toHaveLength(5);
      expect(container.querySelectorAll(".repeated-steps-toggle")).toHaveLength(
        2,
      );
      expect(container.textContent).toContain("1000");
      expect(
        container.querySelector(
          state === "failed" ? ".step-item.failed" : ".step-item .active",
        ),
      ).not.toBeNull();
      if (state === "failed")
        expect(container.textContent).toContain("download failed");
      const toggle = container.querySelector<HTMLButtonElement>(
        ".repeated-steps-toggle",
      )!;
      await act(async () => toggle.click());
      expect(toggle.getAttribute("aria-expanded")).toBe("true");
      expect(
        container.querySelectorAll(".repeated-steps-items .step-item"),
      ).toHaveLength(1000);
      await act(async () => toggle.click());
      expect(container.querySelectorAll(".step-item")).toHaveLength(5);
      expect(container.querySelector(".repeated-steps-items")).toBeNull();
    } finally {
      await act(async () => root.unmount());
      vi.unstubAllGlobals();
    }
  },
);

it("uses each substep's own failure and skipped state instead of failing the last row", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  await i18n.changeLanguage("en");
  const task = taskStatus("base", "base#failed", "failed");
  task.state = "failed";
  task.error = "parent error";
  const step = task.steps[0];
  task.steps = [
    { ...step, name: "execute", state: "failed", percentage: null },
    {
      ...step,
      name: "download",
      parent: "execute",
      state: "missed",
      error: "deadline missed",
      percentage: null,
    },
    { ...step, name: "publish", parent: "execute", state: "skipped" },
  ];
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    await act(async () => root.render(<ExecutionSteps task={task} />));
    expect(container.querySelectorAll(".step-item.failed")).toHaveLength(2);
    expect(container.querySelectorAll(".step-substep")).toHaveLength(2);
    expect(container.querySelectorAll(".step-item")[1].textContent).toContain(
      "deadline missed",
    );
    const last = container.querySelectorAll(".step-item")[2];
    expect(last.classList.contains("failed")).toBe(false);
    expect(last.querySelector(".done")).toBeNull();
    expect(last.textContent).toContain("Skipped");
  } finally {
    await act(async () => root.unmount());
    vi.unstubAllGlobals();
  }
});
