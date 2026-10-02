import { axonx } from "../../shared/api/client";
import type { MachineInfo, MachineNode } from "./types";

interface TargetStatus {
  address: string;
  healthy: boolean;
}

export function machineFromTargetAddress(id: string): MachineNode | null {
  const match = /^(?:https:\/\/)?(?:\[[^\]]+\]|[^:/?#]+):([0-9]{1,5})$/.exec(
    id,
  );
  if (!match || Number(match[1]) < 1 || Number(match[1]) > 65535) return null;
  const address = id.startsWith("https://") ? id : `http://${id}`;
  try {
    const url = new URL(address);
    if (
      !["http:", "https:"].includes(url.protocol) ||
      !url.hostname ||
      url.username ||
      url.password ||
      url.pathname !== "/" ||
      url.search ||
      url.hash
    )
      return null;
    return { id, address, isLocal: false, healthy: false };
  } catch {
    return null;
  }
}

export const machineStatus = (target?: string, signal?: AbortSignal) =>
  axonx.invoke<MachineInfo>("machine_status", {}, { target, signal });

export async function listMachineOptions(
  signal?: AbortSignal,
): Promise<MachineNode[]> {
  const targets = await axonx.invoke<TargetStatus[]>(
    "list_machines",
    {},
    { signal },
  );
  const localAddress =
    new URL(axonx.baseUrl || window.location.href, window.location.href).host ||
    "localhost";
  return [
    { id: "local", address: localAddress, isLocal: true, healthy: true },
    ...targets.map((target) => ({
      id: target.address.replace(/^http:\/\//, ""),
      address: target.address,
      isLocal: false,
      healthy: target.healthy,
    })),
  ];
}
