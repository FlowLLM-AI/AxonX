import { expect, it } from "vitest";
import { schedules, taskStatus } from "../../playground/fixtures";
import type { Schedule, TaskSummary } from "../tasks/types";
import type { ScheduleTrigger } from "../../shared/api/contracts";
import {
  buildOperationIndex,
  findOperationEntry,
  isEarlierSubmission,
  searchOperationIndex,
} from "./model";

function task(source: ScheduleTrigger | null, name = "download"): TaskSummary {
  return {
    ...taskStatus("api", `api#download#${name}`, "download"),
    display_name: name,
    category: "data_update",
    source: { kind: "submit", schedule: source },
    is_online: false,
    is_replica: false,
    step_progress: null,
  };
}
const schedule = (): Schedule =>
  structuredClone(schedules.find((item) => item.name === "data_update")!);

it.each([null, "invalid", "2026-10-21T00:00:00Z", "2026-10-21T01:00:01Z"])(
  "does not treat a failure as superseded without a later creation time (%s)",
  (created_at) => {
    const current = schedule();
    current.arguments = { task: "download", task_name: "manual" };
    current.last_trigger = {
      ...current.last_trigger!,
      state: "failed",
      triggered_at: "2026-10-21T01:00:00Z",
      finished_at: "2026-10-21T01:00:01Z",
    };
    const actual = {
      ...task(null, "manual"),
      created_at,
      started_at: "2026-10-21T05:00:00Z",
    };
    expect(isEarlierSubmission(current, actual)).toBe(false);
    actual.created_at = "2026-10-21T05:00:00Z";
    expect(isEarlierSubmission(current, actual)).toBe(true);
    expect(isEarlierSubmission(current)).toBe(false);
    expect(
      isEarlierSubmission(current, {
        ...actual,
        task_id: "api#download#other",
      }),
    ).toBe(false);
    expect(
      isEarlierSubmission(current, {
        ...actual,
        source: { kind: "submit", schedule: current.last_trigger },
      }),
    ).toBe(false);
    expect(
      isEarlierSubmission(
        {
          ...current,
          last_trigger: { ...current.last_trigger, state: "running" },
        },
        actual,
      ),
    ).toBe(false);
  },
);

it("attaches configuration to exact scheduled Tasks without adding a configuration row", () => {
  const first = schedule();
  const second = {
    ...first,
    name: "second",
    scheduler_id: "second",
    history: [],
    last_trigger: null,
  };
  const manual = task(null, "manual");
  const entries = buildOperationIndex(
    [first.name, second.name],
    [first, second],
    [
      task(first.last_trigger),
      task(
        {
          ...first.last_trigger!,
          name: second.name,
          scheduler_id: second.scheduler_id,
        },
        "second",
      ),
      manual,
    ],
  );
  expect(entries.map((entry) => entry.kind)).toEqual(["task", "task", "task"]);
  expect(entries.map((entry) => entry.schedules)).toEqual([
    [first],
    [second],
    [],
  ]);
  expect(manual.source.schedule).toBeNull();
});

it("merges a fixed-name schedule into the same manual Task without changing its provenance", () => {
  const current = schedule();
  current.arguments = { task: "download", task_name: "manual" };
  const manual = task(null, "manual");
  const entries = buildOperationIndex([current.name], [current], [manual]);
  expect(entries).toHaveLength(1);
  expect(entries[0].id).toBe(manual.task_id);
  expect(entries[0].schedules).toEqual([current]);
  expect(manual.source.schedule).toBeNull();
  expect(
    findOperationEntry(entries, [current], `schedule:${current.name}`),
  ).toBe(entries[0]);
  expect(
    findOperationEntry(
      entries,
      [current],
      `trigger:${current.last_trigger!.trigger_id}`,
    ),
  ).toBe(entries[0]);
  expect(findOperationEntry(entries, [current], "unrelated")).toBeUndefined();
});

it.each([true, false])(
  "opens the Task that owns an older submission, including sliced trigger history (%s)",
  (retained) => {
    const current = schedule();
    const old = { ...current.last_trigger!, trigger_id: "older-submit" };
    current.history = retained ? [old] : [];
    const older = { ...task(old, "older"), started_at: "2026-01-04T09:00:00Z" };
    const latest = task(current.last_trigger, "latest");
    const entries = buildOperationIndex(
      [current.name],
      [current],
      [older, latest],
    );
    expect(entries[0].id).toBe(latest.task_id);
    expect(
      findOperationEntry(entries, [current], "trigger:older-submit")?.id,
    ).toBe(older.task_id);
    expect(
      findOperationEntry(entries, [current], `schedule:${current.name}`)?.id,
    ).toBe(latest.task_id);
  },
);

it.each([
  { task: "other", task_name: "manual" },
  { task: "download", task_name: "other" },
  { task: "download" },
  { task: "download", task_name: "" },
  { task: "download", task_name: 123 },
])(
  "keeps a configuration separate when its target is not the exact manual Task: %j",
  (args) => {
    const current = { ...schedule(), arguments: args };
    const entries = buildOperationIndex(
      [current.name],
      [current],
      [task(null, "manual")],
    );
    expect(entries.map((entry) => entry.kind)).toEqual(["task", "schedule"]);
    expect(entries[0].schedules).toEqual([]);
  },
);

it("retains multiple configurations targeting one Task without duplicate Task rows", () => {
  const first = {
    ...schedule(),
    arguments: { task: "download", task_name: "manual" },
  };
  const second = { ...first, name: "second", scheduler_id: "second" };
  const entries = buildOperationIndex(
    [first.name, second.name],
    [first, second],
    [task(null, "manual")],
  );
  expect(entries).toHaveLength(1);
  expect(entries[0].schedules).toEqual([first, second]);
});

it("does not infer schedule provenance from a same-name scheduler on a new service", () => {
  const current = schedule();
  const old = {
    ...current.last_trigger!,
    scheduler_id: "old-service",
    trigger_id: "old-trigger",
  };
  const actual = task(old);
  const entries = buildOperationIndex([current.name], [current], [actual]);
  expect(entries.map((entry) => entry.kind)).toEqual(["task", "schedule"]);
  expect(entries[0].schedules).toHaveLength(0);
  expect(actual.source.schedule).toEqual(old);
  current.history = [old];
  expect(buildOperationIndex([current.name], [current], [actual])).toHaveLength(
    1,
  );
});

it("deduplicates Job triggers and retains their configuration in the execution detail", () => {
  const current = schedule();
  current.job = "sync_flush";
  current.last_trigger = { ...current.last_trigger!, job: current.job };
  const failed = {
    ...current.last_trigger,
    trigger_id: "failed-job",
    state: "failed" as const,
    error: "Rejected",
  };
  current.history = [failed, current.last_trigger];
  const entries = buildOperationIndex(
    [current.name],
    [current],
    [task(current.last_trigger)],
  );
  expect(entries.map((entry) => entry.kind).sort()).toEqual(["job", "task"]);
  expect(entries.find((entry) => entry.kind === "job")?.id).toBe(
    "trigger:failed-job",
  );
  expect(buildOperationIndex([current.name], [current], [])).toHaveLength(2);
});

it.each(["running", "succeeded", "failed", "cancelled"] as const)(
  "omits %s submit rows and retains a configuration entry when no Task exists",
  (state) => {
    const current = schedule();
    current.last_trigger = { ...current.last_trigger!, state };
    current.history = [current.last_trigger];
    const entries = buildOperationIndex([current.name], [current], []);
    expect(entries).toHaveLength(1);
    expect(entries[0].kind).toBe("schedule");
    expect(entries[0].schedules[0].last_trigger?.state).toBe(state);
    expect(current.history).toEqual([current.last_trigger]);
  },
);

it("omits older submissions after a same-name Task is replaced, including a failed replacement", () => {
  const current = schedule();
  current.history = [
    { ...current.last_trigger!, trigger_id: "previous-submit" },
  ];
  const actual = { ...task(current.last_trigger), state: "failed" as const };
  const entries = buildOperationIndex([current.name], [current], [actual]);
  expect(entries.map((entry) => entry.id)).toEqual([actual.task_id]);
  expect(current.history).toHaveLength(1);
});

it("searches Task identity and attached configuration without creating duplicate rows or mutating entries", () => {
  const current = schedule();
  const entries = buildOperationIndex(
    [current.name],
    [current],
    [task(current.last_trigger), task(null, "manual")],
  );
  expect(
    searchOperationIndex(entries, "manual").map((entry) => entry.id),
  ).toEqual(["api#download#manual"]);
  expect(searchOperationIndex(entries, "0 17")).toHaveLength(1);
  expect(searchOperationIndex(entries, "synthetic")).toHaveLength(1);
  expect(entries).toHaveLength(2);
  const empty = buildOperationIndex(
    [current.name],
    [{ ...current, history: [], last_trigger: null }],
    [],
  );
  expect(searchOperationIndex(empty, "0 17")).toHaveLength(1);
});

it("uses retained scheduler identity when history is sliced and preserves missing configuration access", () => {
  const current = {
    ...schedule(),
    history: [],
    history_scheduler_ids: ["old-service"],
  };
  const old = {
    ...current.last_trigger!,
    scheduler_id: "old-service",
    trigger_id: "before-window",
  };
  expect(
    buildOperationIndex([current.name], [current], [task(old)]),
  ).toHaveLength(1);
  expect(buildOperationIndex([current.name], [], [])[0]).toEqual({
    kind: "schedule",
    id: `schedule:${current.name}`,
    name: current.name,
    schedules: [],
  });
});
