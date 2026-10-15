export type {
  CpuInfo,
  MemoryInfo,
  GpuInfo,
  MachineInfo,
} from "../../shared/api/contracts";
import type { MachineInfo } from "../../shared/api/contracts";

export interface MachineNode {
  id: string;
  address: string;
  isLocal: boolean;
  healthy: boolean;
  info?: MachineInfo;
}
