/** Narrow JSON object values at transport and file boundaries. */
export const isRecord = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);

export const selectOptions = (
  values: readonly string[],
  labels: Record<string, string> = {},
) => values.map((value) => ({ value, label: labels[value] || value }));
