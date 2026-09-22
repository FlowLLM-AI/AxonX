import { useCallback, useEffect, useMemo, useState } from "react";
import {
  listMachineOptions,
  machineHost,
  machineStatus,
} from "../features/machines/api";
import type { MachineNode } from "../features/machines/types";
import type { ContextOption, ThemePreference } from "./types";
import { parseHash, routeHash, type AppRoute } from "./routes";
import { axonx, AxonXError } from "../shared/api/client";

const LOCAL_MACHINE: MachineNode = {
  id: "local",
  address: "localhost",
  isLocal: true,
  healthy: true,
};
const DEFAULT_SIDEBAR_WIDTH = 248;

function storedSidebarWidth() {
  const value = Number(localStorage.getItem("axonx-sidebar-width"));
  return value >= 190 && value <= 360 ? value : DEFAULT_SIDEBAR_WIDTH;
}

function useLocation() {
  const [location, setLocation] = useState(() =>
    parseHash(window.location.hash),
  );

  useEffect(() => {
    if (!window.location.hash) window.location.hash = "m/local/runtime/tasks";
    const sync = () => setLocation(parseHash(window.location.hash));
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  const setRoute = useCallback(
    (route: AppRoute, machineId = location.machineId, replace = false) => {
      const hash = routeHash(machineId, route);
      if (replace) window.history.replaceState(null, "", hash);
      else if (window.location.hash !== hash) window.location.hash = hash;
      setLocation({ machineId, route });
    },
    [location.machineId],
  );

  return {
    ...location,
    navigate: useCallback(
      (route: AppRoute, machineId?: string) => setRoute(route, machineId),
      [setRoute],
    ),
    replace: useCallback(
      (route: AppRoute, machineId?: string) => setRoute(route, machineId, true),
      [setRoute],
    ),
  };
}

function useTheme() {
  const [theme, setTheme] = useState<ThemePreference>(() => {
    const saved = localStorage.getItem("axonx-theme");
    return saved === "light" || saved === "dark" ? saved : "system";
  });

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme =
        theme === "dark" || (theme === "system" && media.matches)
          ? "dark"
          : "light";
    };
    localStorage.setItem("axonx-theme", theme);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);

  return { theme, setTheme };
}

function useMachines(
  machineId: string,
  onMissing: (machineId: string) => void,
  authRevision: number,
) {
  const [machines, setMachines] = useState<MachineNode[]>([LOCAL_MACHINE]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    listMachineOptions(controller.signal)
      .then((result) => {
        setMachines(result);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!controller.signal.aborted) setLoaded(true);
      });
    return () => controller.abort();
  }, [authRevision]);

  useEffect(() => {
    if (loaded && !machines.some((machine) => machine.id === machineId))
      onMissing("local");
  }, [loaded, machineId, machines, onMissing]);

  const selectedMachine = useMemo(
    () => machines.find((machine) => machine.id === machineId) || machines[0],
    [machineId, machines],
  );
  return {
    machines,
    selectedMachine,
    remoteIp: selectedMachine.isLocal
      ? undefined
      : machineHost(selectedMachine.address),
  };
}

function useServiceStatus(remoteIp: string | undefined, authRevision: number) {
  const [serviceOnline, setServiceOnline] = useState<boolean | null>(null);
  const [authRequired, setAuthRequired] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setServiceOnline(null);
    setAuthRequired(false);
    const check = () =>
      machineStatus(remoteIp, controller.signal)
        .then(() => {
          setServiceOnline(true);
          setAuthRequired(false);
        })
        .catch((reason: unknown) => {
          if (!(
            reason instanceof DOMException && reason.name === "AbortError"
          )) {
            setServiceOnline(false);
            setAuthRequired(
              reason instanceof AxonXError && reason.status === 401,
            );
          }
        });
    void check();
    const timer = window.setInterval(check, 15_000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [authRevision, remoteIp]);

  return { serviceOnline, setServiceOnline, authRequired };
}

export function useStudio() {
  const { machineId, route, navigate, replace } = useLocation();
  const theme = useTheme();
  const [authRevision, setAuthRevision] = useState(0);
  const setAuthToken = useCallback((token: string) => {
    axonx.setToken(token);
    setAuthRevision((revision) => revision + 1);
  }, []);
  const navigateToMachine = useCallback(
    (nextMachineId: string) => navigate(route, nextMachineId),
    [navigate, route],
  );
  const machineState = useMachines(machineId, navigateToMachine, authRevision);
  const service = useServiceStatus(machineState.remoteIp, authRevision);
  const [resourceOptions, setResourceOptions] = useState<ContextOption[]>([]);
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("axonx-sidebar") === "collapsed",
  );
  const [sidebarWidth, setSidebarWidth] = useState(storedSidebarWidth);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => setResourceOptions([]), [machineId, route]);

  const sidebar = {
    collapsed,
    width: sidebarWidth,
    mobileOpen,
    setMobileOpen,
    toggle: () =>
      setCollapsed((current) => {
        localStorage.setItem(
          "axonx-sidebar",
          current ? "expanded" : "collapsed",
        );
        return !current;
      }),
    resize: (width: number) => {
      setCollapsed(false);
      setSidebarWidth(width);
    },
    finishResize: (width: number) => {
      const collapse = width < 160;
      setCollapsed(collapse);
      setSidebarWidth(collapse ? storedSidebarWidth() : width);
      localStorage.setItem(
        "axonx-sidebar",
        collapse ? "collapsed" : "expanded",
      );
      if (!collapse) localStorage.setItem("axonx-sidebar-width", String(width));
    },
  };

  return {
    ...theme,
    ...machineState,
    ...service,
    authRevision,
    authTokenConfigured: axonx.hasToken(),
    setAuthToken,
    route,
    navigate,
    replace,
    resourceOptions,
    setResourceOptions,
    sidebar,
  };
}

export type SidebarState = ReturnType<typeof useStudio>["sidebar"];
