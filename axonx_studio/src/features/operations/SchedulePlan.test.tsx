// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { schedules, taskStatus } from "../../playground/fixtures";
import type { Schedule } from "../tasks/types";
import { SchedulePlan, SchedulePlanButton } from "./SchedulePlan";
import type { ScheduleTask } from "./model";

let root: Root;
let container: HTMLDivElement;
let schedule: Schedule;
beforeEach(async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  await i18n.changeLanguage("en");
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  schedule = structuredClone(schedules[0]);
  schedule.cron = "0 9 * * 1-5";
  schedule.next_run_at = "2026-10-22T01:00:00Z";
  schedule.last_trigger = {
    ...schedule.last_trigger!,
    triggered_at: "2026-10-21T01:00:00Z",
    finished_at: "2026-10-21T01:00:01Z",
    state: "failed",
    error:
      "FileExistsError: Active Task already exists: composite#a_stock_online#axon2-core",
  };
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
  await i18n.changeLanguage("en");
});
const render = async (items = [schedule], task?: ScheduleTask) =>
  act(async () =>
    root.render(
      <>
        <SchedulePlanButton
          schedules={items}
          task={task}
          open
          onToggle={() => {}}
          panelId="plan"
        />
        <SchedulePlan schedules={items} task={task} id="plan" />
      </>,
    ),
  );

it.each(["en", "zh"])(
  "explains the past submission conflict in %s without exposing a second report",
  async (language) => {
    await i18n.changeLanguage(language);
    await render();
    const facts = container.querySelector(".schedule-plan-facts")!.textContent!;
    expect(facts).toContain(
      language === "zh" ? "工作日 09:00" : "Weekdays at 09:00",
    );
    expect(facts).toContain("10/22");
    expect(facts).toContain("09:00");
    const last = container.querySelector(".schedule-plan-last")!.textContent!;
    expect(last).toContain("10/21");
    expect(last).toContain(
      language === "zh" ? "同名活动任务记录" : "active Task record",
    );
    expect(last).toContain(i18n.t("operations.plan.submissionHistory"));
    expect(container.querySelector('[role="status"]')).not.toBeNull();
    expect(
      container.querySelector(".schedule-plan-toggle .schedule-plan-warning"),
    ).not.toBeNull();
    expect(last).not.toContain("FileExistsError");
    expect(container.querySelector("h2, [role='tab']")).toBeNull();
    const technical = container.querySelector<HTMLDetailsElement>(
      ".schedule-plan-technical",
    )!;
    expect(technical.open).toBe(false);
    expect(
      JSON.parse(technical.querySelector("pre")!.textContent!),
    ).toMatchObject({
      cron: schedule.cron,
      arguments: schedule.arguments,
      last_trigger: schedule.last_trigger,
    });
  },
);

it.each(["running", "failed", "succeeded"] as const)(
  "keeps an earlier rejection as neutral history when a newer Task is %s",
  async (state) => {
    schedule.arguments = { task: "download", task_name: "demo" };
    const current = {
      ...taskStatus("api", "api#download#demo", "download"),
      state,
      created_at: "2026-10-21T05:26:04Z",
    };
    await render([schedule], current);
    expect(container.querySelector(".schedule-plan-last")?.classList).toContain(
      "is-history",
    );
    expect(
      container.querySelector(".schedule-plan-last")?.textContent,
    ).toContain("The current Task was created afterward.");
    expect(
      container.querySelector('[role="status"], .schedule-plan-warning'),
    ).toBeNull();
    expect(container.querySelector("button")?.getAttribute("aria-label")).toBe(
      "Schedule plan",
    );
    expect(
      JSON.parse(container.querySelector("pre")!.textContent!).last_trigger,
    ).toEqual(schedule.last_trigger);
    expect(current.state).toBe(state);
    expect(current.source.schedule).toBeNull();
  },
);

it("still warns for a later rejection when another plan has older history", async () => {
  schedule.arguments = { task: "download", task_name: "demo" };
  const current = {
    ...taskStatus("api", "api#download#demo", "download"),
    created_at: "2026-10-21T05:26:04Z",
  };
  const later = {
    ...schedule,
    name: "later-plan",
    last_trigger: {
      ...schedule.last_trigger!,
      triggered_at: "2026-10-21T06:00:00Z",
      finished_at: "2026-10-21T06:00:01Z",
    },
  };
  await render([schedule, later], current);
  expect(
    container.querySelectorAll(".schedule-plan-last.is-history"),
  ).toHaveLength(1);
  expect(container.querySelectorAll('[role="status"]')).toHaveLength(1);
  expect(
    container
      .querySelector(".schedule-plan-toggle")
      ?.getAttribute("aria-label"),
  ).toContain("Last submission failed");
});

it("uses the schedule timezone and retains custom timing in technical details", async () => {
  schedule.timezone = "UTC";
  schedule.cron = "*/10 * * * *";
  schedule.last_trigger = null;
  await render();
  expect(
    container.querySelector(".schedule-plan-facts")!.textContent,
  ).toContain("Custom schedule · UTC");
  expect(
    container.querySelector(".schedule-plan-facts")!.textContent,
  ).toContain("01:00");
  expect(container.querySelector(".schedule-plan-last")!.textContent).toContain(
    "No triggers yet",
  );
  expect(container.querySelector("pre")!.textContent).toContain(schedule.cron);
});

it.each(["queued", "running", "succeeded", "failed", "cancelled"] as const)(
  "keeps %s submission status distinct from Task status",
  async (state) => {
    schedule.cron = "5 9 * * *";
    schedule.next_run_at = null;
    schedule.last_trigger = {
      ...schedule.last_trigger!,
      state,
      error: "Other error",
    };
    await render();
    expect(
      container.querySelector(".schedule-plan-facts")!.textContent,
    ).toContain("Daily at 09:05");
    expect(
      container.querySelector(".schedule-plan-facts")!.textContent,
    ).toContain("—");
    expect(
      container.querySelector(".schedule-plan-last")!.textContent,
    ).toContain(i18n.t(`operations.plan.states.${state}`));
    expect(
      container.querySelector(".schedule-plan-last")!.textContent,
    ).not.toContain("same-name Task");
    expect(container.querySelector("pre")!.textContent).toContain(
      "Other error",
    );
  },
);

it("identifies each plan when more than one schedule targets the Task", async () => {
  await render([
    schedule,
    { ...schedule, name: "second-plan", cron: "0 10 * * 1-5" },
  ]);
  expect(container.querySelectorAll(".schedule-plan-item")).toHaveLength(2);
  expect(
    container.querySelectorAll(".schedule-plan-item > strong")[1].textContent,
  ).toBe("second-plan");
});
