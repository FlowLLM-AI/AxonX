import type { ApiResponse, MachineInfo, MachineNode, TaskInfo, TaskStatus } from "./types";

const configuredUrl = import.meta.env.VITE_AXONX_API_URL || "";
export const API_URL = configuredUrl.replace(/\/$/, "");

async function parse<T>(response: Response): Promise<T> {
  let payload: ApiResponse<T> | { detail?: string };
  try {
    payload = await response.json();
  } catch {
    throw new Error(`Invalid server response (HTTP ${response.status})`);
  }
  if (!response.ok) {
    throw new Error("detail" in payload && payload.detail ? payload.detail : `HTTP ${response.status}`);
  }
  const result = payload as ApiResponse<T>;
  if (!result.success) throw new Error(String(result.answer || "Request failed"));
  return result.answer;
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

export const listTaskStatuses = (signal?: AbortSignal) =>
  callJob<TaskStatus[]>("list_runtime_task_statuses", {}, signal);
export const listInstalledTaskInfos = (signal?: AbortSignal) =>
  callJob<TaskInfo[]>("list_installed_task_infos", {}, signal);
export const cancelTask = (taskId: string) => callJob<boolean>("cancel", { task_id: taskId });
export const submitTask = (task: string, values: Record<string, unknown>) =>
  callJob<{ accepted: boolean; task: string }>("submit", { task, ...values });

interface RemoteMachineStatus { address: string; healthy: boolean }

function addressHost(address: string) {
  if (address.startsWith("[")) return address.slice(1, address.indexOf("]"));
  const separator = address.lastIndexOf(":");
  return separator < 0 ? address : address.slice(0, separator);
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
