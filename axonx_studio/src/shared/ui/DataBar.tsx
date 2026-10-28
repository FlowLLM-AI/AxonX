import type { ReactNode } from "react";
import { toNumber } from "../lib/format";

export function DataBar({
  value,
  domain,
  children,
}: {
  value: number;
  domain?: { min: number; max: number };
  children: ReactNode;
}) {
  const numeric = value;
  const zero = domain
    ? (-domain.min / (domain.max - domain.min || 1)) * 100
    : 0;
  const position = Number.isFinite(numeric)
    ? domain && numeric < 0
      ? zero + (numeric / (domain.max - domain.min || 1)) * 100
      : zero
    : 0;
  const width = Number.isFinite(numeric)
    ? Math.abs(numeric / ((domain?.max ?? 0) - (domain?.min ?? 0) || 1)) * 100
    : 0;
  return (
    <span className="summary-data-cell">
      {domain && domain.min < 0 && domain.max > 0 && (
        <span
          className="summary-data-zero"
          style={{ left: `${zero}%` }}
          aria-hidden="true"
        />
      )}
      {domain && width > 0 && (
        <span
          className={`summary-data-bar${numeric < 0 ? " negative" : ""}`}
          style={{ left: `${position}%`, width: `${width}%` }}
          aria-hidden="true"
        />
      )}
      <span className="summary-data-value">{children}</span>
    </span>
  );
}

export function DataCell({
  value,
  format,
  domain,
}: {
  value: unknown;
  format: (value: unknown) => string;
  domain?: { min: number; max: number };
}) {
  return (
    <DataBar value={toNumber(value)} domain={domain}>
      {format(value)}
    </DataBar>
  );
}
