import { useCallback, useEffect } from "react";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { machineStatus } from "./api";

export function useMachineInfo(
  target: string | undefined,
  onConnection: (online: boolean) => void,
) {
  const request = useCallback(
    (signal: AbortSignal) => machineStatus(target, signal),
    [target],
  );
  const resource = useAsyncResource(request);

  useEffect(() => {
    if (resource.data) onConnection(true);
    else if (resource.error) onConnection(false);
  }, [onConnection, resource.data, resource.error]);

  return resource;
}
