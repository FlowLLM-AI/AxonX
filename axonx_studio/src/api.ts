import type { ApiResponse, JobInfo, MachineInfo, MachineNode, PluginInfo, TaskInfo, TaskLogChunk, TaskStatus, WorkspaceDirectory, WorkspacePreview } from "./types";

const configuredUrl = import.meta.env.VITE_AXONX_API_URL || "";
export const API_URL = configuredUrl.replace(/\/$/, "");

async function parse<T>(response: Response): Promise<T> {
  let payload: ApiResponse<T> | { detail?: unknown };
  try {
    payload = await response.json();
  } catch {
    throw new Error(`Invalid server response (HTTP ${response.status})`);
  }
  if (!response.ok) {
    const detail = "detail" in payload ? payload.detail : undefined;
    throw new Error(typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : `HTTP ${response.status}`);
  }
  const result = payload as ApiResponse<T>;
  if (!result.success) throw new Error(String(result.answer || "Request failed"));
  return result.answer;
}

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = await response.json() as { detail?: unknown };
      if (typeof payload.detail === "string") detail = payload.detail;
      else if (payload.detail) detail = JSON.stringify(payload.detail);
    } catch { /* Preserve the HTTP status when the body is not JSON. */ }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export async function callJob<T>(name: string, body: Record<string, unknown> = {}, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_URL}/jobs/${encodeURIComponent(name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  return parse<T>(response);
}

const remoteBody = (remoteIp?: string) => remoteIp ? { remote_ip: remoteIp } : {};

export const listTaskStatuses = (remoteIp?: string, signal?: AbortSignal) =>
  callJob<TaskStatus[]>("list_runtime_task_statuses", remoteBody(remoteIp), signal);
export const getTaskStatus = (taskId: string, remoteIp?: string, signal?: AbortSignal) =>
  callJob<TaskStatus>("status", { task_id: taskId, ...remoteBody(remoteIp) }, signal);
export const readTaskLog = (taskId: string, offset = -1, limit = 65_536, remoteIp?: string, signal?: AbortSignal) =>
  callJob<TaskLogChunk>("read_task_log", { task_id: taskId, offset, limit, ...remoteBody(remoteIp) }, signal);
export const listInstalledTaskInfos = (remoteIp?: string, signal?: AbortSignal) =>
  callJob<TaskInfo[]>("list_installed_task_infos", remoteBody(remoteIp), signal);
export const cancelTask = (taskId: string, remoteIp?: string) => callJob<boolean>("cancel", { task_id: taskId, ...remoteBody(remoteIp) });
export const deleteTasks = (taskIds: string[], remoteIp?: string) => callJob<string[]>("delete_tasks", { task_ids: taskIds, ...remoteBody(remoteIp) });
export const submitTask = (task: string, values: Record<string, unknown>, remoteIp?: string) =>
  callJob<{ accepted: boolean; task: string }>("submit", { task, ...values, ...remoteBody(remoteIp) });
export const machineStatus = (remoteIp?: string, signal?: AbortSignal) =>
  callJob<MachineInfo>("machine_status", remoteBody(remoteIp), signal);
export const listPlugins = (remoteIp?: string, signal?: AbortSignal) =>
  callJob<PluginInfo[]>("list_plugins", remoteBody(remoteIp), signal);
export const listWorkspaceEntries = (path = "", remoteIp?: string, signal?: AbortSignal) =>
  callJob<WorkspaceDirectory>("list_workspace_entries", { path, ...remoteBody(remoteIp) }, signal);
export const previewWorkspaceFile = (path: string, offset = 0, limit = 200, remoteIp?: string, signal?: AbortSignal) =>
  callJob<WorkspacePreview>("preview_workspace_file", { path, offset, limit, ...remoteBody(remoteIp) }, signal);
export const deleteWorkspaceEntry = (path: string, remoteIp?: string) =>
  callJob<{ deleted: string; kind: "file" | "directory" }>("delete_workspace_entry", { path, ...remoteBody(remoteIp) });
export const deleteWorkspaceEntries = (paths: string[], remoteIp?: string) =>
  callJob<{ deleted: { deleted: string; kind: "file" | "directory" }[] }>("delete_workspace_entries", { paths, ...remoteBody(remoteIp) });

export const listJobs = (remoteAddress?: string, signal?: AbortSignal) => {
  const base = remoteAddress ? `${window.location.protocol}//${remoteAddress}` : API_URL;
  return fetch(`${base}/jobs`, { signal }).then(parseJson<JobInfo[]>);
};

export const invokeApi = <T = unknown>(name: string, body: Record<string, unknown>, remoteAddress?: string, signal?: AbortSignal) => {
  const base = remoteAddress ? `${window.location.protocol}//${remoteAddress}` : API_URL;
  return fetch(`${base}/jobs/${encodeURIComponent(name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  }).then(parse<T>);
};

interface RemoteMachineStatus { address: string; healthy: boolean }

function addressHost(address: string) {
  if (address.startsWith("[")) return address.slice(1, address.indexOf("]"));
  const separator = address.lastIndexOf(":");
  return separator < 0 ? address : address.slice(0, separator);
}

export const machineHost = addressHost;

export async function listMachineOptions(signal?: AbortSignal): Promise<MachineNode[]> {
  const remotes = await callJob<RemoteMachineStatus[]>("list_machines", {}, signal);
  const localAddress = new URL(API_URL || window.location.href, window.location.href).host || "localhost";
  return [
    { id: "local", address: localAddress, isLocal: true, healthy: true },
    ...remotes.map((remote) => ({ id: remote.address, address: remote.address, isLocal: false, healthy: remote.healthy })),
  ];
}

export async function listMachineResources(): Promise<MachineNode[]> {
  const [local, remotes] = await Promise.all([
    callJob<MachineInfo>("machine_status"),
    callJob<RemoteMachineStatus[]>("list_machines"),
  ]);
  const remoteNodes = await Promise.all(remotes.map(async (remote): Promise<MachineNode> => {
    const base = { id: remote.address, address: remote.address, isLocal: false, healthy: remote.healthy };
    if (!remote.healthy) return base;
    try {
      const info = await callJob<MachineInfo>("machine_status", { remote_ip: addressHost(remote.address) });
      return { ...base, info };
    } catch {
      return { ...base, healthy: false };
    }
  }));
  const localAddress = new URL(API_URL || window.location.href, window.location.href).host || "localhost";
  return [{ id: "local", address: localAddress, isLocal: true, healthy: true, info: local }, ...remoteNodes];
}
