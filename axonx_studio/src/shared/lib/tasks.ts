/** Canonical workspace directory derived from a validated Task ID. */
export const taskDirectory = (taskId: string) =>
  `${taskId.split("#")[0]}/${taskId}`;
