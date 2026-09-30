import { describe, expect, it } from "vitest";
import { parseSourceTasks } from "./sourceTasks";

describe("source task metadata", () => {
  it("reads single and multiple dependencies from strings", () => {
    expect(parseSourceTasks("train#native#model")).toEqual([
      "train#native#model",
    ]);
    expect(parseSourceTasks("etl#native#prices, train#native#model")).toEqual([
      "etl#native#prices",
      "train#native#model",
    ]);
  });

  it("has no dependencies for empty, missing, or old array values", () => {
    expect(parseSourceTasks("")).toEqual([]);
    expect(parseSourceTasks(undefined)).toEqual([]);
    expect(parseSourceTasks(["etl#native#prices"])).toEqual([]);
  });
});
