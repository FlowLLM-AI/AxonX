import { describe, expect, it } from "vitest";
import { taskStatus } from "../../playground/data";
import type { TaskSummary } from "../../shared/api/contracts";
import { taskStepProgress } from "./model";

describe("task summary progress", () => {
  it("preserves the step index without the historical steps", () => {
    const full = taskStatus("api", "api#test#summary");
    const { input_params, output_params, steps, children, ...metadata } = full;
    void input_params;
    void output_params;
    void children;
    void steps;
    const summary: TaskSummary = {
      ...metadata,
      display_name: "test",
      is_replica: false,
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
