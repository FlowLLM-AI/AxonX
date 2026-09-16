import { useEffect, useState } from "react";
import { machineStatus } from "../../features/machines/api";

export function useServiceStatus(remoteIp?: string) {
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const check = () =>
      machineStatus(remoteIp, controller.signal)
        .then(() => setOnline(true))
        .catch((reason: unknown) => {
          if (!(reason instanceof DOMException && reason.name === "AbortError"))
            setOnline(false);
        });

    void check();
    const timer = window.setInterval(check, 15_000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [remoteIp]);

  return [online, setOnline] as const;
}
