import { Send, Square } from "lucide-react";
import { useTranslation } from "react-i18next";

export function Composer({
  value,
  running,
  canStop,
  onChange,
  onSend,
  onStop,
}: {
  value: string;
  running: boolean;
  canStop: boolean;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="agent-composer-wrap">
      <div className="agent-composer">
        <textarea
          value={value}
          rows={1}
          placeholder={t("agent.composerPlaceholder")}
          disabled={running}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              if (!running && value.trim()) onSend();
            }
          }}
        />
        {running ? (
          <button
            className="agent-stop"
            onClick={onStop}
            disabled={!canStop}
            title={t("agent.stop")}
          >
            <Square />
          </button>
        ) : (
          <button
            className="agent-send"
            onClick={onSend}
            disabled={!value.trim()}
            title={t("agent.send")}
          >
            <Send />
          </button>
        )}
      </div>
      <small>{t("agent.composerHint")}</small>
    </div>
  );
}
