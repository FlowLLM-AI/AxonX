import { useCallback, useEffect, useState } from "react";
import { parseHash, routeHash } from "../routes";
import type { AppRoute } from "../routes";

export function useHashRoute() {
  const [location, setLocation] = useState(() =>
    parseHash(window.location.hash),
  );

  useEffect(() => {
    if (!window.location.hash) window.location.hash = "m/local/home/overview";
    const handleChange = () => setLocation(parseHash(window.location.hash));
    window.addEventListener("hashchange", handleChange);
    return () => window.removeEventListener("hashchange", handleChange);
  }, []);

  const navigate = useCallback(
    (route: AppRoute, machineId = location.machineId) => {
      const nextHash = routeHash(machineId, route);
      if (window.location.hash === nextHash) setLocation({ machineId, route });
      else window.location.hash = nextHash;
    },
    [location.machineId],
  );

  return { ...location, navigate };
}
