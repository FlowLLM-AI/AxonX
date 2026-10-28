import { afterEach, expect, it, vi } from "vitest";
import { taskStatus } from "../../playground/data";
import { axonx } from "../../shared/api/client";
import { getResearchTask, listResearchTasks } from "./api";

afterEach(() => vi.restoreAllMocks());

it("queries only successful results of the selected category and reuses the wire record", async () => {
  const task = taskStatus("train", "train#sample");
  const invoke = vi.spyOn(axonx, "invoke").mockResolvedValue([task]);
  const controller = new AbortController();
  const result = await listResearchTasks("train", {
    target: "remote",
    signal: controller.signal,
  });
  expect(invoke).toHaveBeenCalledOnce();
  expect(invoke).toHaveBeenCalledWith(
    "list_task_statuses",
    { detail: "summary", task_type: "train", state: "succeeded" },
    { target: "remote", signal: controller.signal },
  );
  expect(result[0]).toBe(task);
});

it("rejects a result cancelled while the request was pending", async () => {
  const controller = new AbortController();
  vi.spyOn(axonx, "invoke").mockImplementation(async () => {
    controller.abort();
    return [];
  });
  await expect(
    listResearchTasks("etl", { signal: controller.signal }),
  ).rejects.toMatchObject({ name: "AbortError" });
});

it("checks selected task identity and category before exposing a research output", async () => {
  const task = taskStatus("train", "train#sample");
  const invoke = vi.spyOn(axonx, "invoke").mockResolvedValue(task);
  expect(
    await getResearchTask("train", task.task_id, { target: "remote" }),
  ).toBe(task);
  expect(invoke).toHaveBeenLastCalledWith(
    "status",
    { task_id: task.task_id },
    { target: "remote", signal: undefined },
  );
  await expect(getResearchTask("predict", task.task_id)).rejects.toThrow(
    "Research task changed",
  );
  await expect(getResearchTask("train", "train#another")).rejects.toThrow(
    "Research task changed",
  );
});
