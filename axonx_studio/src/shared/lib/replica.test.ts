import { expect, it } from "vitest";
import { taskStatus } from "../../playground/data";
import { displayArtifacts } from "../api/artifacts";

it("uses actual sampled revisions and excludes omitted artifact links", () => {
  const metadata = taskStatus("etl", "etl#demo#test");
  metadata.output_params.artifacts = {
    dataset: { path: "dataset.parquet", size: 1000, revision: "1000:1" },
    omitted: { path: "missing.parquet", size: 1000, revision: "1000:1" },
  };
  metadata.replica = {
    purpose: "display",
    snapshot: null,
    log: null,
    source_revision: "1:1",
    policy_revision: "1:1",
    files: {
      "dataset.parquet": {
        size: 100,
        revision: "actual",
        sampled: true,
        rows: 10,
        source_rows: 100,
        dates: ["20260106"],
      },
    },
    omitted: { "missing.parquet": "budget" },
    source_log_path: "",
  };
  expect(displayArtifacts(metadata)).toEqual({
    dataset: {
      path: "dataset.parquet",
      size: 100,
      revision: "actual",
    },
  });
  expect(metadata.output_params.artifacts).toHaveProperty("omitted");
});
