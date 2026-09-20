export interface CpuInfo {
  total_cores: number | null;
  physical_cores: number | null;
  usage_percent: number;
}

export interface MemoryInfo {
  total_bytes: number;
  used_bytes: number;
  available_bytes: number;
  usage_percent: number;
}

export interface GpuInfo {
  vendor: "nvidia" | "amd";
  index: number;
  uuid: string | null;
  name: string | null;
  memory_total_bytes: number | null;
  memory_used_bytes: number | null;
  memory_available_bytes: number | null;
  memory_usage_percent: number | null;
  usage_percent: number | null;
}

export interface MachineInfo {
  axonx: {
    version: string;
    git_commit: string | null;
    git_branch: string | null;
  };
  cpu: CpuInfo;
  memory: MemoryInfo;
  gpus: GpuInfo[];
}

export interface MachineNode {
  id: string;
  address: string;
  isLocal: boolean;
  healthy: boolean;
  info?: MachineInfo;
}
