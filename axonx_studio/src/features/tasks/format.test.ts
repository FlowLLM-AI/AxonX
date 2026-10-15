import { describe, expect, it } from "vitest";
import { taskStepProgress } from "./format";
import { taskStatus } from "../../playground/fixtures";
import type { TaskSummary } from "./types";

describe("task summary progress", () => {
  it("preserves the step index without the historical steps", () => {
    const full = taskStatus("api", "api#test#summary", "test");
    const { input_params, output_params, steps, children, ...metadata } = full;
    void input_params;
    void output_params;
    void children;
    void steps;
    const summary: TaskSummary = {
      ...metadata,
      display_name: "test",
      is_replica: false,
      is_online: false,
      step_progress: {
        current: 24000,
        total: 24001,
        name: "download",
        percentage: 42.6,
      },
    };
    expect(taskStepProgress(summary)).toMatchObject({
      current: 24000,
      name: "download",
      percentage: 43,
    });
    expect(taskStepProgress({ ...summary, step_progress: null })).toBeNull();
  });
});
