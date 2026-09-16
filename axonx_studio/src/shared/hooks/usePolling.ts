import { useEffect, useState } from "react";

export function usePolling(
  callback: () => void,
  enabled: boolean,
  intervalSeconds: number,
) {
  const [seconds, setSeconds] = useState(intervalSeconds);

  useEffect(() => {
    setSeconds(intervalSeconds);
    if (!enabled) return;
    const timer = window.setInterval(() => {
      setSeconds((current) => {
        if (current <= 1) {
          callback();
          return intervalSeconds;
        }
        return current - 1;
      });
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [callback, enabled, intervalSeconds]);

  return seconds;
}
