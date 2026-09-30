export function parseSourceTasks(value: unknown): string[] {
  return typeof value === "string" && value.trim()
    ? value.split(",").map((item) => item.trim())
    : [];
}
