import { getTaskStatus } from "./api";
import type { ChildTaskRecord, TaskMetadata } from "./types";

export interface TaskNode {
  record: ChildTaskRecord;
  status: TaskMetadata | null;
  error: string;
}

/** Follow exact owned Runs, including nested download and ETL chains. */
export async function readTaskChildren(
  parent: TaskMetadata,
  target: string | undefined,
  signal: AbortSignal,
  messages: { replaced: string; snapshot: string },
): Promise<TaskNode[]> {
  const visited = new Set([`${parent.task_id}:${parent.run_id}`]);
  const requests = new Map<string, Promise<TaskMetadata>>();
  async function visit(owner: TaskMetadata): Promise<TaskNode[]> {
    const records = [
      ...new Map(
        owner.children.filter((c) => c.task_id).map((c) => [c.task_id!, c]),
      ).values(),
    ];
    const branches = await Promise.all(
      records.map(async (record): Promise<TaskNode[]> => {
        const identity = `${record.task_id}:${record.run_id}`;
        if (visited.has(identity)) return [];
        visited.add(identity);
        try {
          if (!requests.has(record.task_id!))
            requests.set(
              record.task_id!,
              getTaskStatus(record.task_id!, target, signal),
            );
          const status = await requests.get(record.task_id!)!;
          if (status.run_id !== record.run_id)
            return [{ record, status: null, error: messages.replaced }];
          if (
            parent.replica?.snapshot &&
            status.replica?.snapshot?.revision !==
              parent.replica.snapshot.revision
          )
            return [{ record, status: null, error: messages.snapshot }];
          return [{ record, status, error: "" }, ...(await visit(status))];
        } catch (reason) {
          signal.throwIfAborted();
          return [{ record, status: null, error: String(reason) }];
        }
      }),
    );
    return branches.flat();
  }
  return visit(parent);
}
