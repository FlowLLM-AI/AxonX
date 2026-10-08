import { resolvedLocale } from "../../i18n";

export const fmt = (value: unknown, digits = 2) => {
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
