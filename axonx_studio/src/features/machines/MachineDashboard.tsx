import { Cpu, Gauge, HardDrive, MemoryStick, Microchip } from "lucide-react";
import { t } from "../../i18n";
import { formatBytes } from "../../shared/lib/format";
import type { Language } from "../../app/types";
import type { GpuInfo, MachineNode } from "./types";

export function MachineDashboard({
  node,
  language,
}: {
  node: MachineNode;
  language: Language;
}) {
  const text = t(language);
  const info = node.info;
  if (!info) return null;
  const estimatedUsedCores =
    info.cpu.total_cores == null
      ? null
      : Math.round(info.cpu.total_cores * info.cpu.usage_percent) / 100;

  return (
    <>
      <section className="machine-resource-group host-resource-section">
        <div className="section-title">
          <div>
            <Cpu />
            <span>{language === "zh" ? "CPU 与内存" : "CPU & memory"}</span>
          </div>
          <small>4 METRICS</small>
        </div>
        <div className="resource-grid">
          <ResourceGauge
            label={text.cpuUsage}
            value={info.cpu.usage_percent}
            tone="cpu"
            icon={<Cpu />}
            detail={`${estimatedUsedCores ?? "—"} / ${info.cpu.total_cores ?? "—"} ${text.coresUsed}`}
          />
          <ResourceGauge
            label={text.memoryUsage}
            value={info.memory.usage_percent}
            tone="memory"
            icon={<MemoryStick />}
            detail={`${formatBytes(info.memory.available_bytes)} ${text.available}`}
          />
          <article className="capacity-card">
            <header>
              <span>
                <Gauge />
                {text.cpuCapacity}
              </span>
              <small>CPU</small>
            </header>
            <CapacityRow
              label={text.totalCores}
              value={`${info.cpu.total_cores ?? "—"}`}
              percent={info.cpu.total_cores == null ? 0 : 100}
            />
            <CapacityRow
              label={text.physicalCores}
              value={`${info.cpu.physical_cores ?? "—"}`}
              percent={
                info.cpu.physical_cores && info.cpu.total_cores
                  ? (info.cpu.physical_cores / info.cpu.total_cores) * 100
                  : 0
              }
            />
            <CapacityRow
              label={text.coresUsed}
              value={`${estimatedUsedCores ?? "—"}`}
              percent={info.cpu.usage_percent}
            />
          </article>
          <article className="capacity-card memory-card">
            <header>
              <span>
                <HardDrive />
                {text.memoryCapacity}
              </span>
              <small>RAM</small>
            </header>
            <CapacityRow
              label={text.usedMemory}
              value={formatBytes(info.memory.used_bytes)}
              percent={info.memory.usage_percent}
            />
            <CapacityRow
              label={text.available}
              value={formatBytes(info.memory.available_bytes)}
              percent={100 - info.memory.usage_percent}
            />
            <CapacityRow
              label={text.totalMemory}
              value={formatBytes(info.memory.total_bytes)}
              percent={100}
            />
          </article>
        </div>
      </section>
      <section className="machine-resource-group gpu-section">
        <div className="section-title">
          <div>
            <Microchip />
            <span>{text.gpuResources}</span>
          </div>
          <small>{info.gpus.length} DEVICES</small>
        </div>
        {info.gpus.length ? (
          <div className="gpu-grid">
            {info.gpus.map((gpu) => (
              <GpuCard
                key={`${gpu.vendor}-${gpu.index}`}
                gpu={gpu}
                language={language}
              />
            ))}
          </div>
        ) : (
          <div className="no-gpu">
            <span>
              <Microchip />
            </span>
            <div>
              <strong>{text.noGpu}</strong>
              <small>{text.noGpuHint}</small>
            </div>
          </div>
        )}
      </section>
    </>
  );
}

function ResourceGauge({
  label,
  value,
  tone,
  icon,
  detail,
}: {
  label: string;
  value: number;
  tone: string;
  icon: React.ReactNode;
  detail: string;
}) {
  const safe = Math.max(0, Math.min(100, value));
  return (
    <article className={`resource-gauge-card ${tone}`}>
      <header>
        <span>
          {icon}
          {label}
        </span>
        <i className="live-wave">
          <b />
          <b />
          <b />
        </i>
      </header>
      <div
        className="gauge-ring"
        style={{
          background: `conic-gradient(var(--gauge) ${safe}%, var(--surface-3) 0)`,
        }}
      >
        <div>
          <strong>
            {safe.toFixed(1)}
            <small>%</small>
          </strong>
          <span>LIVE</span>
        </div>
      </div>
      <p>{detail}</p>
    </article>
  );
}

function CapacityRow({
  label,
  value,
  percent,
}: {
  label: string;
  value: string;
  percent: number;
}) {
  return (
    <div className="capacity-row">
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <div>
        <i style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} />
      </div>
    </div>
  );
}

function GpuCard({ gpu, language }: { gpu: GpuInfo; language: Language }) {
  const text = t(language);
  return (
    <article className="gpu-card">
      <header>
        <span>
          {gpu.vendor.toUpperCase()} · GPU {gpu.index}
        </span>
        <strong>{gpu.name || "GPU"}</strong>
      </header>
      <div>
        <CapacityRow
          label={text.gpuUtilization}
          value={gpu.usage_percent == null ? "—" : `${gpu.usage_percent}%`}
          percent={gpu.usage_percent || 0}
        />
        <CapacityRow
          label={text.gpuMemory}
          value={
            gpu.memory_used_bytes == null
              ? "—"
              : `${formatBytes(gpu.memory_used_bytes)} / ${formatBytes(gpu.memory_total_bytes || 0)}`
          }
          percent={gpu.memory_usage_percent || 0}
        />
      </div>
    </article>
  );
}
