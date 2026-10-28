import { playground } from "../../app/environment";
import {
  axonx,
  type AxonXClient,
  type RequestOptions,
} from "../../shared/api/client";
import type { MachineInfo } from "../../shared/api/contracts";

export interface MachineNode {
  id: string;
  address: string;
  isLocal: boolean;
  healthy: boolean;
  info?: MachineInfo;
}

interface TargetStatus {
  address: string;
  healthy: boolean;
}

interface StatusRequest {
  controller: AbortController;
  users: number;
  promise: Promise<MachineInfo>;
}

const statusRequests = new WeakMap<AxonXClient, Map<string, StatusRequest>>();

/** Share only in-flight reads; each subscriber owns its cancellation. */
export function machineStatus({
  target,
  signal,
}: RequestOptions = {}): Promise<MachineInfo> {
  if (signal?.aborted) return Promise.reject(signal.reason);
  let pending = statusRequests.get(axonx);
  if (!pending) {
    pending = new Map();
    statusRequests.set(axonx, pending);
  }
  const requests = pending;
  const key = JSON.stringify([target, axonx.authRevision]);
  let request = requests.get(key);
  if (!request) {
    const controller = new AbortController();
    const created: StatusRequest = {
      controller,
      users: 0,
      promise: axonx
        .invoke<MachineInfo>(
          "machine_status",
          {},
          { target, signal: controller.signal },
        )
        .finally(() => {
          if (requests.get(key) === created) requests.delete(key);
        }),
    };
    requests.set(key, created);
    request = created;
  }
  const shared = request;
  shared.users += 1;
  return new Promise<MachineInfo>((resolve, reject) => {
    let active = true;
    const release = () => {
      if (!active) return;
      active = false;
      signal?.removeEventListener("abort", abort);
      shared.users -= 1;
      if (!shared.users && requests.get(key) === shared) {
        requests.delete(key);
        shared.controller.abort();
      }
    };
    const abort = () => {
      release();
      reject(signal!.reason);
    };
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) abort();
    shared.promise.then(
      (value) => {
        release();
        resolve(value);
      },
      (reason) => {
        release();
        reject(reason);
      },
    );
  });
}

export async function listMachineOptions(
  options: Pick<RequestOptions, "signal"> = {},
): Promise<MachineNode[]> {
  const targets = await axonx.invoke<TargetStatus[]>(
    "list_machines",
    {},
    options,
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
