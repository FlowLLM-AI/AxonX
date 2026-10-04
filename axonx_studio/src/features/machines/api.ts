import { playground } from "../../app/environment";
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
  const localAddress = playground
    ? "Browser simulation"
    : window.location.host || "localhost";
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
