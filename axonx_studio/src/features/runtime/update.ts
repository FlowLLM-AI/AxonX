import { axonx, type RequestOptions } from "../../shared/api/client";

const operationJobs = {
  git: "update_from_git",
  pip: "update_from_pip",
  restart: "restart_service",
};

export type UpdateMode = keyof typeof operationJobs;

interface UpdateRecord {
  update_id: string;
  mode: UpdateMode;
  phase: string;
  error: string | null;
  before: Record<string, string | null>;
  after: Record<string, string | null> | null;
  commit: string | null;
}

export interface UpdateStatus {
  record: UpdateRecord | null;
  log: string;
}

export async function listUpdateModes(options: RequestOptions = {}) {
  const catalog = await axonx.jobs(options);
  const jobs = new Set(catalog.items.map((job) => job.name));
  return jobs.has("get_update_status")
    ? (Object.keys(operationJobs) as UpdateMode[]).filter((mode) =>
        jobs.has(operationJobs[mode]),
      )
    : [];
}

export const getUpdateStatus = (
  updateId: string | undefined,
  options: RequestOptions = {},
) =>
  axonx.invoke<UpdateStatus>(
    "get_update_status",
    updateId ? { update_id: updateId } : {},
    options,
  );

export const startUpdate = (mode: UpdateMode, options: RequestOptions = {}) =>
  axonx.invoke<UpdateRecord>(operationJobs[mode], {}, options);
