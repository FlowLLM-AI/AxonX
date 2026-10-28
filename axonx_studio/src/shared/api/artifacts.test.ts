import { expect, it } from "vitest";
import { taskStatus } from "../../playground/data";
import { displayArtifacts, isArtifactRecord } from "./artifacts";

it("accepts sampled replica revisions for artifact loading", () => {
  const task = taskStatus("etl", "etl#demo#test");
  task.output_params.artifacts = {
    dataset: { path: "dataset.parquet", size: 100, revision: "100:1" },
  };
  task.replica = {
    purpose: "display",
    snapshot: null,
    log: null,
    source_revision: "run:1",
    policy_revision: "display:3",
    files: {
      "dataset.parquet": {
        size: 10,
        revision: "100:1:['20260106']",
        sampled: true,
        rows: 1,
        source_rows: 10,
        dates: ["20260106"],
      },
    },
    omitted: {},
    source_log_path: "",
  };
  expect(isArtifactRecord(displayArtifacts(task).dataset)).toBe(true);
  expect(
    isArtifactRecord({
      path: "dataset.parquet",
      size: 10,
      sha256: "a".repeat(64),
    }),
  ).toBe(false);
});
