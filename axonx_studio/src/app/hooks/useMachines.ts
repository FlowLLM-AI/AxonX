import { useCallback, useEffect, useMemo, useState } from "react";
import { listMachineOptions, machineHost } from "../../features/machines/api";
import type { MachineNode } from "../../features/machines/types";

const fallbackMachine: MachineNode = {
  id: "local",
  address: "localhost",
  isLocal: true,
  healthy: true,
};

export function useMachines(
  machineId: string,
  onMachineChange: (machineId: string) => void,
) {
  const [machines, setMachines] = useState<MachineNode[]>([fallbackMachine]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    if (loaded || loading) return;
    setLoading(true);
    try {
      const result = await listMachineOptions();
      setMachines(result);
      setLoaded(true);
      if (!result.some((machine) => machine.id === machineId))
        onMachineChange("local");
    } catch {
      // The service status hook owns the visible connection state. Keep the local fallback usable.
      setLoaded(true);
    } finally {
      setLoading(false);
    }
  }, [loaded, loading, machineId, onMachineChange]);

  useEffect(() => {
    void load();
  }, [load]);

  const selectedMachine = useMemo(
    () => machines.find((machine) => machine.id === machineId) || machines[0],
    [machineId, machines],
  );
  const remoteIp = selectedMachine?.isLocal
    ? undefined
    : machineHost(selectedMachine.address);

  useEffect(
    () => localStorage.setItem("axonx-machine", machineId),
    [machineId],
  );

  return { machines, selectedMachine, remoteIp, loading };
}
