import { useCallback, useEffect, useRef, type ReactNode } from "react";
import {
  GitBranch,
  GitCommitHorizontal,
  LoaderCircle,
  Server,
  Settings2,
  Tag,
  X,
} from "lucide-react";
import { machineStatus } from "../machines/api";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import type { Language, MachineNode } from "../../types";

export function EnvironmentSettingsModal({
  language,
  machine,
  remoteIp,
  onClose,
}: {
  language: Language;
  machine: MachineNode;
  remoteIp?: string;
  onClose: () => void;
}) {
  const zh = language === "zh";
  const closeButton = useRef<HTMLButtonElement>(null);
  const loadStatus = useCallback(
    (signal: AbortSignal) => machineStatus(remoteIp, signal),
    [remoteIp],
  );
  const { data: info, loading, error } = useAsyncResource(
    loadStatus,
  );

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    closeButton.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previousFocus?.focus();
    };
  }, [onClose]);

  return (
    <div className="settings-backdrop" onMouseDown={onClose}>
      <section
        className="settings-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="settings-dialog-header">
          <span className="settings-dialog-icon"><Settings2 /></span>
          <div>
            <small>AXONX STUDIO</small>
            <h2 id="settings-title">{zh ? "设置" : "Settings"}</h2>
          </div>
          <button
            ref={closeButton}
            className="settings-close"
            onClick={onClose}
            aria-label={zh ? "关闭设置" : "Close settings"}
          >
            <X />
          </button>
        </header>
        <div className="settings-dialog-body">
          <div className="settings-section-heading">
            <div>
              <span className="settings-kicker">{zh ? "当前机器" : "CURRENT MACHINE"}</span>
              <h3>{zh ? "运行环境" : "Environment"}</h3>
              <p>{zh ? "版本与代码信息" : "Version and source details"}</p>
            </div>
          </div>
          {loading && !info ? (
            <div className="settings-message"><LoaderCircle className="spin" />{zh ? "正在读取运行环境…" : "Loading environment…"}</div>
          ) : error ? (
            <div className="settings-message settings-error">
              <Server />
              <span>{zh ? "无法读取运行环境" : "Environment unavailable"}<small>{error}</small></span>
            </div>
          ) : info ? (
            <div className="settings-info-grid">
              <InfoItem icon={<Tag />} label={zh ? "AxonX 版本" : "AXONX VERSION"} value={`v${info.axonx.version}`} />
              <InfoItem icon={<GitCommitHorizontal />} label="GIT COMMIT" value={info.axonx.git_commit || "—"} />
              <InfoItem icon={<GitBranch />} label="GIT BRANCH" value={info.axonx.git_branch || "—"} />
              <InfoItem icon={<Server />} label={zh ? "服务地址" : "ENDPOINT"} value={machine.address} />
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function InfoItem({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="settings-info-item">
      <span className="settings-info-icon">{icon}</span>
      <div>
        <small>{label}</small>
        <strong title={value}>{value}</strong>
      </div>
    </div>
  );
}
