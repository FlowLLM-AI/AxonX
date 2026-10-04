import { useEffect, useState } from "react";
import { startPolling } from "../lib/polling";

export function usePolling(
  callback: (signal: AbortSignal) => Promise<void>,
  enabled: boolean,
  intervalSeconds: number,
  immediate = false,
) {
  const [seconds, setSeconds] = useState(intervalSeconds);

  useEffect(() => {
    setSeconds(intervalSeconds);
    if (!enabled) return;
    return startPolling(callback, intervalSeconds, setSeconds, immediate);
  }, [callback, enabled, intervalSeconds, immediate]);

  return seconds;
}
