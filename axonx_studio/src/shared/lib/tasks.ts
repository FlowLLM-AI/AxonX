/** Canonical workspace directory derived from a validated Task ID. */
export function taskDirectory(taskId: string): string {
  const [kind, , name] = taskId.split("#");
  let generated = false;
  if (/^[0-9]{10}[A-Za-z0-9]{4}$/.test(name) && Number(name.slice(0, 4)) > 0) {
    const date = new Date(
      `${name.slice(0, 4)}-${name.slice(4, 6)}-${name.slice(6, 8)}T${name.slice(8, 10)}:00:00Z`,
    );
    generated =
      Number.isFinite(date.getTime()) &&
      date.toISOString().slice(0, 13).replace(/\D/g, "") === name.slice(0, 10);
  }
  return `${generated ? "tmp/tasks" : "tasks"}/${kind}/${taskId}`;
}

export function upstreamTaskIds(value: unknown): string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
    ? [...value]
    : [];
}
