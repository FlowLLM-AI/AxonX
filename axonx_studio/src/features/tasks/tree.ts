import type { ChildTaskRecord, TaskMetadata } from "../../shared/api/contracts";
import { getTaskStatus } from "./api";

export interface TaskNode {
  record: ChildTaskRecord;
  status: TaskMetadata | null;
  error: string;
  issue?: "replaced" | "snapshot";
}

/** Follow recorded child Tasks, including nested download and ETL chains. */
export async function readTaskChildren(
  parent: TaskMetadata,
  target: string | undefined,
  signal: AbortSignal,
  messages: { replaced: string; snapshot: string },
): Promise<TaskNode[]> {
  const visited = new Set([`${parent.task_id}:${parent.started_at}`]);
  const requests = new Map<string, Promise<TaskMetadata>>();
  async function visit(owner: TaskMetadata): Promise<TaskNode[]> {
    const records = [
      ...new Map(
        owner.children
          .filter((c) => c.child_task_id)
          .map((c) => [c.child_task_id!, c]),
      ).values(),
    ];
    const branches = await Promise.all(
      records.map(async (record): Promise<TaskNode[]> => {
        if (record.started_at === null)
          return [{ record, status: null, error: "" }];
        const identity = `${record.child_task_id}:${record.started_at}`;
        if (visited.has(identity)) return [];
        visited.add(identity);
        try {
          if (!requests.has(record.child_task_id!))
            requests.set(
              record.child_task_id!,
              getTaskStatus(record.child_task_id!, { target, signal }),
            );
          const status = await requests.get(record.child_task_id!)!;
          if (status.started_at !== record.started_at)
            return [
              {
                record,
                status: null,
                error: messages.replaced,
                issue: "replaced",
              },
            ];
          if (
            parent.replica?.snapshot &&
            status.replica?.snapshot?.revision !==
              parent.replica.snapshot.revision
          )
            return [
              {
                record,
                status: null,
                error: messages.snapshot,
                issue: "snapshot",
              },
            ];
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
