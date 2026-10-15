import { expect, it } from "vitest";
import { displayArtifacts } from "./replica";
import { taskStatus } from "../../playground/fixtures";

it("uses actual sampled hashes and excludes omitted artifact links", () => {
  const metadata = taskStatus("etl", "etl#demo#test", "test");
  metadata.output_params.artifacts = {
    dataset: { path: "dataset.parquet", size: 1000, sha256: "original" },
    omitted: { path: "missing.parquet", size: 1000, sha256: "original" },
  };
  metadata.replica = {
    purpose: "display",
    snapshot: null,
    log: null,
    source_digest: "a".repeat(64),
    policy_digest: "b".repeat(64),
    files: {
      "dataset.parquet": {
        size: 100,
        sha256: "actual",
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
    dataset: { path: "dataset.parquet", size: 100, sha256: "actual" },
  });
  expect(metadata.output_params.artifacts).toHaveProperty("omitted");
});
