import { axonx } from "../../shared/api/client";
import type { MachineInfo, MachineNode } from "./types";

interface TargetStatus {
  address: string;
  healthy: boolean;
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
      id: target.address,
      address: target.address,
      isLocal: false,
      healthy: target.healthy,
    })),
  ];
}
