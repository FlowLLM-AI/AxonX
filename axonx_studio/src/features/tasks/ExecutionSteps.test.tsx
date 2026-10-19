// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { taskStatus } from "../../playground/fixtures";
import { ExecutionSteps } from "./ExecutionSteps";

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
