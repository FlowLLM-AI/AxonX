import { resolvedLocale } from "../../i18n";

export function formatMachineAddress(address: string): string {
  return address.replace(/^https?:\/\//, "");
}

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
): string {
  if (value === null || value === undefined || value === "") return "—";
  return new Intl.DateTimeFormat(resolvedLocale(), {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

export const toNumber = (value: unknown): number =>
  value == null || value === "" ? NaN : Number(value);
export const formatFixed = (value: unknown, digits = 2): string =>
  Number.isFinite(toNumber(value)) ? toNumber(value).toFixed(digits) : "—";
export const formatPercent = (value: unknown): string =>
  Number.isFinite(toNumber(value))
    ? `${(toNumber(value) * 100).toFixed(2)}%`
    : "—";
export const dateInput = (value: string): string =>
  `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
export const compactDate = (value: string): string => value.replaceAll("-", "");

export const formatNumber = (value: unknown, digits = 2) => {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  if (Math.abs(number) >= 1_000_000)
    return new Intl.NumberFormat(resolvedLocale(), {
      notation: "compact",
      maximumFractionDigits: 2,
    }).format(number);
  return number.toLocaleString(resolvedLocale(), {
    maximumFractionDigits: digits,
  });
};

export type ValueFormat = "percent" | "score" | "integer" | "boolean";

export const formatTableValue = (value: unknown, format?: ValueFormat) => {
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
