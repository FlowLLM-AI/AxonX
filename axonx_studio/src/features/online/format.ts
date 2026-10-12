import type { Column } from "./ReportTable";

export const display = (value: unknown, format?: Column["format"]) => {
  if (value == null || value === "") return "—";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "—";
    return format === "percent"
      ? `${(value * 100).toFixed(2)}%`
      : format === "score"
        ? value.toFixed(4)
        : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
  }
  return typeof value === "object" ? JSON.stringify(value) : String(value);
};
