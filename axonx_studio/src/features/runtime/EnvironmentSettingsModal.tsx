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
import type { MachineNode } from "../machines/types";
import { useTranslation } from "react-i18next";

export function EnvironmentSettingsModal({
  machine,
  remoteIp,
  onClose,
}: {
  machine: MachineNode;
  remoteIp?: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const closeButton = useRef<HTMLButtonElement>(null);
  const loadStatus = useCallback(
    (signal: AbortSignal) => machineStatus(remoteIp, signal),
    [remoteIp],
  );
  const { data: info, loading, error } = useAsyncResource(loadStatus);

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
          <span className="settings-dialog-icon">
            <Settings2 />
          </span>
          <div>
            <small>AXONX STUDIO</small>
            <h2 id="settings-title">{t("shell.settings")}</h2>
          </div>
          <button
            ref={closeButton}
            className="settings-close"
            onClick={onClose}
            aria-label={t("runtimeSettings.close")}
          >
            <X />
          </button>
        </header>
        <div className="settings-dialog-body">
          <div className="settings-section-heading">
            <div>
              <span className="settings-kicker">
                {t("runtimeSettings.currentMachine")}
              </span>
              <h3>{t("runtimeSettings.environment")}</h3>
              <p>{t("runtimeSettings.versionSource")}</p>
            </div>
          </div>
          {loading && !info ? (
            <div className="settings-message">
              <LoaderCircle className="spin" />
              {t("runtimeSettings.loading")}
            </div>
          ) : error ? (
            <div className="settings-message settings-error">
              <Server />
              <span>
                {t("runtimeSettings.unavailable")}
                <small>{error}</small>
              </span>
            </div>
          ) : info ? (
            <div className="settings-info-grid">
              <InfoItem
                icon={<Tag />}
                label={t("runtimeSettings.axonxVersion")}
                value={`v${info.axonx.version}`}
              />
              <InfoItem
                icon={<GitCommitHorizontal />}
                label="GIT COMMIT"
                value={info.axonx.git_commit || "—"}
              />
              <InfoItem
                icon={<GitBranch />}
                label="GIT BRANCH"
                value={info.axonx.git_branch || "—"}
              />
              <InfoItem
                icon={<Server />}
                label={t("runtimeSettings.endpoint")}
                value={machine.address}
              />
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function InfoItem({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
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
