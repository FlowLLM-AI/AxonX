/** Canonical workspace directory derived from a validated Task ID. */
export const taskDirectory = (taskId: string) =>
  `${taskId.split("#")[0]}/${taskId}`;

export function upstreamTaskIds(value: unknown): string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
    ? [...value]
    : [];
}
