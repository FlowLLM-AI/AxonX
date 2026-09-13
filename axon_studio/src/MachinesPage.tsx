import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Boxes, CheckCircle2, ChevronRight, CircleOff, Cpu, Gauge, GitCommitHorizontal,
  HardDrive, LoaderCircle, MemoryStick, Microchip, RefreshCw, Server, Wifi,
} from "lucide-react";
import { listMachineResources } from "./api";
import { interpolate, t } from "./i18n";
import type { GpuInfo, Language, MachineNode } from "./types";

export function MachinesPage({ language, onConnection }: { language: Language; onConnection: (online: boolean) => void }) {
  const text = t(language);
  const [nodes, setNodes] = useState<MachineNode[]>([]);
  const [selectedId, setSelectedId] = useState("local");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [seconds, setSeconds] = useState(10);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const load = useCallback(async (quiet = false) => {
    if (quiet) setRefreshing(true); else setLoading(true);
    try {
      const result = await listMachineResources();
      setNodes(result);
      setSelectedId((current) => result.some((node) => node.id === current) ? current : result[0]?.id || "");
      setUpdatedAt(new Date()); setSeconds(10); setError(""); onConnection(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason)); onConnection(false);
    } finally { setLoading(false); setRefreshing(false); }
  }, [onConnection]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(() => setSeconds((value) => {
      if (value <= 1) { void load(true); return 10; }
      return value - 1;
    }), 1000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, load]);

  const selected = nodes.find((node) => node.id === selectedId);
  const totals = useMemo(() => nodes.reduce((result, node) => {
    if (node.healthy) result.online += 1;
    if (node.info) {
      result.cores += node.info.cpu.total_cores;
      result.memory += node.info.memory.total_bytes;
      result.gpus += node.info.gpus?.length || 0;
    }
    return result;
  }, { online: 0, cores: 0, memory: 0, gpus: 0 }), [nodes]);

  return <section className="workspace-page machine-workspace">
    <div className="page-heading">
      <div><p className="eyebrow">MACHINE FLEET / 00</p><h1>{text.machineTitle}</h1><span>{text.machineLead}</span></div>
      <div className="heading-actions">
        <label className="auto-toggle"><input type="checkbox" checked={autoRefresh} onChange={(event) => setAutoRefresh(event.target.checked)} /><i /><span>{text.autoRefresh}<small>{autoRefresh ? interpolate(text.nextRefresh, { seconds }) : "—"}</small></span></label>
        <button className="secondary-button" onClick={() => void load(true)} disabled={refreshing}><RefreshCw size={16} className={refreshing ? "spin" : ""} />{text.refreshNow}</button>
      </div>
    </div>

    <div className="cluster-strip">
      <div className="cluster-title"><span><Boxes /></span><div><small>AXONX FLEET</small><strong>{text.cluster}</strong></div></div>
      <ClusterMetric icon={<Wifi />} label={text.nodesOnline} value={`${totals.online}/${nodes.length || 1}`} tone="green" />
      <ClusterMetric icon={<Cpu />} label={text.cpuCapacity} value={String(totals.cores)} tone="blue" />
      <ClusterMetric icon={<MemoryStick />} label={text.memoryCapacity} value={formatBytes(totals.memory)} tone="cyan" />
      <ClusterMetric icon={<Microchip />} label={text.gpuCapacity} value={String(totals.gpus)} tone="violet" />
    </div>

    {error && <div className="error-banner machine-error"><CircleOff /><div><strong>{text.machineFailed}</strong><span>{error}</span></div><button onClick={() => void load()}>{text.retry}</button></div>}

    <div className="machine-layout">
      <aside className="node-panel">
        <header><div><p>{text.nodeList}</p><span>{interpolate(text.nodeCount, { count: nodes.length })}</span></div><span className="fleet-live"><i /> LIVE</span></header>
        <div className="node-list">
          {nodes.map((node, index) => <button key={node.id} className={selectedId === node.id ? "active" : ""} onClick={() => setSelectedId(node.id)}>
            <span className={`node-icon ${node.healthy ? "healthy" : "offline"}`}><Server /></span>
            <div><strong>{node.isLocal ? text.localNode : `${text.remoteNode} ${index}`}</strong><small>{node.address}</small></div>
            <span className={`node-health ${node.healthy ? "healthy" : "offline"}`}><i />{node.healthy ? text.online : text.offline}</span><ChevronRight />
          </button>)}
          {!loading && !nodes.length && <div className="catalog-empty">{text.selectNode}</div>}
        </div>
      </aside>

      <div className="machine-detail">
        {loading && !selected && <div className="loading-state machine-loading"><LoaderCircle className="spin" /> {text.machineLoading}</div>}
        {selected && selected.info && <MachineDashboard node={selected} language={language} updatedAt={updatedAt} />}
        {selected && !selected.info && <div className="machine-offline"><span><CircleOff /></span><h2>{text.machineUnavailable}</h2><p>{selected.address}</p></div>}
      </div>
    </div>
  </section>;
}

function ClusterMetric({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: string; tone: string }) {
  return <div className={`cluster-metric ${tone}`}><span>{icon}</span><div><small>{label}</small><strong>{value}</strong></div></div>;
}

function MachineDashboard({ node, language, updatedAt }: { node: MachineNode; language: Language; updatedAt: Date | null }) {
  const text = t(language); const info = node.info!;
  return <>
    <header className="machine-head"><div className="machine-identity"><span className="machine-cube"><Server /></span><div><small>{node.isLocal ? text.localNode : text.remoteNode}</small><h2>{node.address}</h2><span><CheckCircle2 /> {text.online}</span></div></div><div className="updated-at"><RefreshCw /><span>{text.lastUpdated}<strong>{updatedAt?.toLocaleTimeString(language === "zh" ? "zh-CN" : "en-US", { hour12: false }) || "—"}</strong></span></div></header>
    <div className="resource-grid">
      <ResourceGauge label={text.cpuUsage} value={info.cpu.usage_percent} tone="cpu" icon={<Cpu />} detail={`${info.cpu.used_cores} / ${info.cpu.total_cores} ${text.coresUsed}`} />
      <ResourceGauge label={text.memoryUsage} value={info.memory.usage_percent} tone="memory" icon={<MemoryStick />} detail={`${formatBytes(info.memory.available_bytes)} ${text.available}`} />
      <article className="capacity-card"><header><span><Gauge />{text.cpuCapacity}</span><small>CPU</small></header><CapacityRow label={text.totalCores} value={`${info.cpu.total_cores}`} percent={100} /><CapacityRow label={text.physicalCores} value={`${info.cpu.physical_cores ?? "—"}`} percent={info.cpu.physical_cores ? info.cpu.physical_cores / info.cpu.total_cores * 100 : 0} /><CapacityRow label={text.coresUsed} value={`${info.cpu.used_cores}`} percent={info.cpu.usage_percent} /></article>
      <article className="capacity-card memory-card"><header><span><HardDrive />{text.memoryCapacity}</span><small>RAM</small></header><CapacityRow label={text.usedMemory} value={formatBytes(info.memory.used_bytes)} percent={info.memory.usage_percent} /><CapacityRow label={text.available} value={formatBytes(info.memory.available_bytes)} percent={100 - info.memory.usage_percent} /><CapacityRow label={text.totalMemory} value={formatBytes(info.memory.total_bytes)} percent={100} /></article>
    </div>
    <section className="gpu-section"><div className="section-title"><div><Microchip /><span>{text.gpuResources}</span></div><small>{info.gpus?.length || 0} DEVICES</small></div>{info.gpus?.length ? <div className="gpu-grid">{info.gpus.map((gpu) => <GpuCard key={`${gpu.vendor}-${gpu.index}`} gpu={gpu} language={language} />)}</div> : <div className="no-gpu"><span><Microchip /></span><div><strong>{text.noGpu}</strong><small>{text.noGpuHint}</small></div></div>}</section>
    <section className="runtime-card"><div className="section-title"><div><GitCommitHorizontal /><span>{text.runtimeInfo}</span></div></div><div className="runtime-values"><div><small>{text.version}</small><strong>v{info.axonx.version}</strong></div><div><small>{text.gitCommit}</small><code>{info.axonx.git_commit?.slice(0, 12) || "—"}</code></div><div><small>{text.endpoint}</small><code>{node.address}</code></div></div></section>
  </>;
}

function ResourceGauge({ label, value, tone, icon, detail }: { label: string; value: number; tone: string; icon: React.ReactNode; detail: string }) {
  const safe = Math.max(0, Math.min(100, value));
  return <article className={`resource-gauge-card ${tone}`}><header><span>{icon}{label}</span><i className="live-wave"><b /><b /><b /></i></header><div className="gauge-ring" style={{ background: `conic-gradient(var(--gauge) ${safe}%, var(--surface-3) 0)` }}><div><strong>{safe.toFixed(1)}<small>%</small></strong><span>LIVE</span></div></div><p>{detail}</p></article>;
}

function CapacityRow({ label, value, percent }: { label: string; value: string; percent: number }) {
  return <div className="capacity-row"><div><span>{label}</span><strong>{value}</strong></div><div><i style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} /></div></div>;
}

function GpuCard({ gpu, language }: { gpu: GpuInfo; language: Language }) {
  const text = t(language);
  return <article className="gpu-card"><header><span>{gpu.vendor.toUpperCase()} · GPU {gpu.index}</span><strong>{gpu.name || "GPU"}</strong></header><div><CapacityRow label={text.gpuUtilization} value={gpu.usage_percent == null ? "—" : `${gpu.usage_percent}%`} percent={gpu.usage_percent || 0} /><CapacityRow label={text.gpuMemory} value={gpu.memory_used_bytes == null ? "—" : `${formatBytes(gpu.memory_used_bytes)} / ${formatBytes(gpu.memory_total_bytes || 0)}`} percent={gpu.memory_usage_percent || 0} /></div></article>;
}

function formatBytes(bytes: number) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const value = bytes / 1024 ** index;
  return `${value >= 10 || index === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[index]}`;
}
