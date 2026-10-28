import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useRefresh } from "../../shared/hooks/useRefresh";
import { Select } from "../../shared/ui/Select";
import {
  getUpdateStatus,
  listUpdateModes,
  startUpdate,
  type UpdateMode,
  type UpdateStatus,
} from "./update";

export function UpdatePanel({ target }: { target?: string }) {
  return <UpdatePanelContent key={target || "local"} target={target} />;
}

function UpdatePanelContent({ target }: { target?: string }) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<UpdateStatus>({
    record: null,
    log: "",
  });
  const [error, setError] = useState("");
  const [submissionError, setSubmissionError] = useState("");
  const [disconnected, setDisconnected] = useState(false);
  const [availableModes, setAvailableModes] = useState<UpdateMode[]>([]);
  const available = availableModes.length > 0;
  const [submitting, setSubmitting] = useState(false);
  const [selectedMode, setSelectedMode] = useState<UpdateMode>("git");
  const mode = availableModes.includes(selectedMode)
    ? selectedMode
    : (availableModes[0] ?? "git");
  const [confirmed, setConfirmed] = useState(false);
  const updateId = status.record?.update_id;
  const active = Boolean(
    status.record && !["failed", "succeeded"].includes(status.record.phase),
  );

  const requestVersion = useRef(0);
  const read = useCallback(
    async (signal: AbortSignal) => {
      const version = requestVersion.current;
      try {
        if (!available) {
          const supported = await listUpdateModes({ target, signal });
          if (signal.aborted || version !== requestVersion.current) return;
          setAvailableModes(supported);
          setError("");
          if (!supported.length) return;
        }
        const result = await getUpdateStatus(active ? updateId : undefined, {
          target,
          signal,
        });
        if (signal.aborted || version !== requestVersion.current) return;
        setStatus(result);
        setDisconnected(false);
        setError("");
      } catch (cause) {
        if (signal.aborted || version !== requestVersion.current) return;
        setDisconnected(active);
        if (!active) setError(String(cause));
      }
    },
    [target, updateId, active, available],
  );

  useRefresh(read, !submitting, true);

  const start = async (signal: AbortSignal) => {
    requestVersion.current += 1;
    setSubmissionError("");
    setSubmitting(true);
    setError("");
    try {
      const record = await startUpdate(mode, { target, signal });
      if (signal.aborted) return;
      setStatus({ record, log: "" });
      setConfirmed(false);
    } catch (cause) {
      if (!signal.aborted) setSubmissionError(String(cause));
    } finally {
      if (!signal.aborted) setSubmitting(false);
    }
  };
  const submissionController = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    submissionController.current = controller;
    return () => controller.abort();
  }, []);

  return (
    <section className="update-panel runtime-environment-card">
      <header>
        <RefreshCw />
        <strong>{t("update.title")}</strong>
      </header>
      <p>{t("update.description")}</p>
      {(error || submissionError) && (
        <p role="alert">{error || submissionError}</p>
      )}
      {!available ? (
        <p>{t("update.unavailable")}</p>
      ) : (
        <>
          <label>
            {t("update.method")}
            <Select
              value={mode}
              disabled={active || submitting}
              onChange={(event) => {
                setSelectedMode(event.target.value as UpdateMode);
                setConfirmed(false);
              }}
            >
              {availableModes.map((mode) => (
                <option key={mode} value={mode}>
                  {t(`update.${mode}`)}
                </option>
              ))}
            </Select>
          </label>
          <p>{t(`update.${mode}Hint`)}</p>
          <label className="update-checkbox">
            <input
              type="checkbox"
              checked={confirmed}
              disabled={active || submitting}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            {t(`update.${mode}Confirm`)}
          </label>
          <button
            className="secondary-button"
            disabled={!confirmed || active || submitting || Boolean(error)}
            onClick={() => {
              if (submissionController.current)
                void start(submissionController.current.signal);
            }}
          >
            <RefreshCw className={active || submitting ? "spin" : ""} />
            {t(mode === "restart" ? "update.startRestart" : "update.start")}
          </button>
        </>
      )}
      {status.record && (
        <div className="update-status" aria-live="polite">
          <strong>
            {disconnected
              ? t("update.reconnecting")
              : t(
                  `update.${status.record.mode === "restart" ? "restartPhases" : "phases"}.${status.record.phase}`,
                  {
                    defaultValue: status.record.phase,
                  },
                )}
          </strong>
          <small>{status.record.update_id}</small>
          {status.record.error && <p role="alert">{status.record.error}</p>}
          {status.record.after && (
            <p>
              AxonX: {status.record.before.axonx || "—"} →{" "}
              {status.record.after.axonx || "—"}
              <br />
              Studio: {status.record.before["axonx-studio"] || "—"} →{" "}
              {status.record.after["axonx-studio"] || "—"}
            </p>
          )}
          {status.record.commit && <code>{status.record.commit}</code>}
          {status.log && <pre className="update-log">{status.log}</pre>}
          {status.record.phase === "succeeded" && (
            <button
              className="secondary-button"
              onClick={() => window.location.reload()}
            >
              {t("update.reload")}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
