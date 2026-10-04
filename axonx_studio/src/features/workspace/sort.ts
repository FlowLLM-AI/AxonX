import type { WorkspaceEntry } from "./types";

function isDateDirectory(entry: WorkspaceEntry) {
  return entry.kind === "directory" && /^(\d{4}|\d{8})$/.test(entry.name);
}

export function sortRawDataEntries(entries: WorkspaceEntry[]) {
  return [...entries].sort((a, b) => {
    const directoryOrder =
      Number(b.kind === "directory") - Number(a.kind === "directory");
    if (directoryOrder) return directoryOrder;
    const aDate = isDateDirectory(a);
    const bDate = isDateDirectory(b);
    if (aDate && bDate) return b.name.localeCompare(a.name);
    return Number(bDate) - Number(aDate) || a.name.localeCompare(b.name);
  });
}
