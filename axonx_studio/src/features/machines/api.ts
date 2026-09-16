import { API_URL, callJob, remoteBody } from "../../shared/api/client";
import type { MachineInfo, MachineNode } from "../../types";

interface RemoteMachineStatus {
  address: string;
  healthy: boolean;
}

export function machineHost(address: string): string {
  if (address.startsWith("[")) return address.slice(1, address.indexOf("]"));
  const separator = address.lastIndexOf(":");
  return separator < 0 ? address : address.slice(0, separator);
}

export const machineStatus = (remoteIp?: string, signal?: AbortSignal) =>
  callJob<MachineInfo>("machine_status", remoteBody(remoteIp), signal);

export async function listMachineOptions(
  signal?: AbortSignal,
): Promise<MachineNode[]> {
  const remotes = await callJob<RemoteMachineStatus[]>(
    "list_machines",
    {},
    signal,
  );
  const localAddress =
    new URL(API_URL || window.location.href, window.location.href).host ||
    "localhost";
  return [
    { id: "local", address: localAddress, isLocal: true, healthy: true },
    ...remotes.map((remote) => ({
      id: remote.address,
      address: remote.address,
      isLocal: false,
      healthy: remote.healthy,
    })),
  ];
}
