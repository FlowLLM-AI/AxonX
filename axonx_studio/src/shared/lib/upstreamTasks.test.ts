import { describe, expect, it } from "vitest";
import { upstreamTaskIds } from "./upstreamTasks";

describe("upstream task metadata", () => {
  it("reads single and multiple dependencies from arrays", () => {
    expect(upstreamTaskIds(["train#native#model"])).toEqual([
      "train#native#model",
    ]);
    expect(
      upstreamTaskIds(["etl#native#prices", "train#native#model"]),
    ).toEqual(["etl#native#prices", "train#native#model"]);
  });

  it("rejects malformed values and keeps the input array isolated", () => {
    expect(upstreamTaskIds("")).toEqual([]);
    expect(upstreamTaskIds(undefined)).toEqual([]);
    expect(upstreamTaskIds(["etl#native#prices", 1])).toEqual([]);
    const upstreamIds = ["etl#native#prices"];
    upstreamTaskIds(upstreamIds).push("train#native#model");
    expect(upstreamIds).toEqual(["etl#native#prices"]);
  });
});
