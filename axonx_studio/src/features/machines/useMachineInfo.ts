import { useCallback, useEffect } from "react";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { machineStatus } from "./api";

export function useMachineInfo(
  remoteIp: string | undefined,
  onConnection: (online: boolean) => void,
) {
  const request = useCallback(
    (signal: AbortSignal) => machineStatus(remoteIp, signal),
    [remoteIp],
  );
  const resource = useAsyncResource(request);

  useEffect(() => {
    if (resource.data) onConnection(true);
    else if (resource.error) onConnection(false);
  }, [onConnection, resource.data, resource.error]);

  return resource;
}
