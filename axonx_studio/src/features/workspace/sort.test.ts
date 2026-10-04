import { describe, expect, it } from "vitest";
import { sortRawDataEntries } from "./sort";
import type { WorkspaceEntry } from "./types";

function entry(
  name: string,
  kind: WorkspaceEntry["kind"] = "directory",
): WorkspaceEntry {
  return {
    name,
    path: `tushare/${name}`,
    kind,
    preview_kind: null,
    supported: false,
    size: null,
    modified_at: 0,
  };
}

describe("raw data directory ordering", () => {
  it.each([
    ["2010", "2025", "2026"],
    ["20260105", "20261231", "20270104"],
  ])("shows newest date directories first: %s, %s, %s", (...names) => {
    const entries = names.map((name) => entry(name));
    expect(sortRawDataEntries(entries).map((item) => item.name)).toEqual(
      [...names].reverse(),
    );
    expect(entries.map((item) => item.name)).toEqual(names);
  });

  it("keeps folders first and ordinary names alphabetical", () => {
    const entries = [
      entry("z.parquet", "file"),
      entry("symbols"),
      entry("2025"),
      entry("archive"),
      entry("2026", "symlink"),
      entry("2026"),
      entry("a.parquet", "file"),
    ];
    expect(
      sortRawDataEntries(entries).map((item) => [item.name, item.kind]),
    ).toEqual([
      ["2026", "directory"],
      ["2025", "directory"],
      ["archive", "directory"],
      ["symbols", "directory"],
      ["2026", "symlink"],
      ["a.parquet", "file"],
      ["z.parquet", "file"],
    ]);
  });

  it("handles an empty directory", () => {
    expect(sortRawDataEntries([])).toEqual([]);
  });
});
