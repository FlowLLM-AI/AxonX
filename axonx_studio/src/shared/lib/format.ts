import type { Language } from "../../app/types";

export function formatBytes(
  value: number | null | undefined,
  binary = true,
): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "—";
  const base = binary ? 1024 : 1000;
  const units = binary
    ? ["B", "KiB", "MiB", "GiB", "TiB"]
    : ["B", "KB", "MB", "GB", "TB"];
  let size = Math.max(0, value);
  let unit = 0;
  while (size >= base && unit < units.length - 1) {
    size /= base;
    unit += 1;
  }
  const digits = unit === 0 ? 0 : size < 10 ? 1 : 0;
  return `${size.toFixed(digits)} ${units[unit]}`;
}

export function formatDateTime(
  value: string | number | Date | null | undefined,
  language: Language,
): string {
  if (value === null || value === undefined || value === "") return "—";
  return new Intl.DateTimeFormat(language === "zh" ? "zh-CN" : "en-US", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(value));
}
