import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { readTaskLog } from "./api";
import { useRefresh } from "../../shared/hooks/useRefresh";
import { useCopyFeedback } from "../../shared/hooks/useCopyFeedback";
import { errorMessage } from "../../shared/lib/errors";
import { formatBytes } from "../../shared/lib/format";
import type { TaskMetadata } from "./types";

const LIMIT = 65_536;
const MAX = 524_288;

type TaskLogProps = {
  task: TaskMetadata;
  target?: string;
  toolbar?: ReactNode;
};

/** Bounded, cancellable log viewer shared by task and pipeline details. */
export function TaskLogPanel(props: TaskLogProps) {
  return (
    <TaskLogContent
      key={`${props.target}:${props.task.task_id}:${props.task.started_at}`}
      {...props}
    />
  );
}

function TaskLogContent({ task, target, toolbar }: TaskLogProps) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [follow, setFollow] = useState(true);
  const [range, setRange] = useState({
    start: 0,
    next: 0,
    size: 0,
    earlier: false,
  });
  const position = useRef(-1);
  const boundary = useRef(0);
  const buffer = useRef("");
  const [trimmed, setTrimmed] = useState(false);
  const pending = useRef<AbortSignal | null>(null);
  const requests = useRef(new Set<AbortController>());
  const viewport = useRef<HTMLPreElement>(null);
  const clipboard = useCopyFeedback();
  const { task_id: id, started_at: startedAt } = task;
  const path = task.log_path || task.replica?.log?.path;
  const load = useCallback(
    async (signal: AbortSignal, offset?: number, prepend = false) => {
      if ((pending.current && !pending.current.aborted) || !path) return;
      const controller = new AbortController();
      requests.current.add(controller);
      signal = AbortSignal.any([signal, controller.signal]);
      pending.current = signal;
      setBusy(true);
      try {
        let at = offset ?? position.current;
        const limit = prepend ? Math.min(LIMIT, boundary.current - at) : LIMIT;
        if (limit <= 0) return;
        for (;;) {
          const chunk = await readTaskLog(
            id,
            at,
            limit,
            target,
            signal,
            startedAt,
          );
          if (signal.aborted) return;
          const replace = at < 0 || chunk.reset;
          const combined = replace
            ? chunk.content
            : prepend
              ? chunk.content + buffer.current
              : buffer.current + chunk.content;
          buffer.current = combined.slice(-MAX);
          setText(buffer.current);
          if (replace) setTrimmed(false);
          else if (combined.length > MAX) setTrimmed(true);
          if (replace || prepend) boundary.current = chunk.start_offset;
          setRange((current) => ({
            start: replace || prepend ? chunk.start_offset : current.start,
            next: prepend ? current.next : chunk.next_offset,
            size: chunk.file_size,
            earlier:
              replace || prepend ? chunk.has_more_before : current.earlier,
          }));
          setError("");
          if (!prepend) position.current = chunk.next_offset;
          if (prepend || !chunk.has_more_after || chunk.next_offset === at)
            break;
          // Catch up immediately; if far behind, retain a bounded live tail.
          at =
            chunk.file_size - chunk.next_offset > MAX ? -1 : chunk.next_offset;
        }
      } catch (reason) {
        if (!signal.aborted) setError(errorMessage(reason));
      } finally {
        requests.current.delete(controller);
        if (pending.current === signal) pending.current = null;
        if (!signal.aborted) setBusy(false);
      }
    },
    [id, startedAt, path, target],
  );
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, task.state]);
  useEffect(() => {
    const owned = requests.current;
    return () => {
      for (const controller of owned) controller.abort();
    };
  }, []);
  useRefresh(load, follow);
  useEffect(() => {
    if (follow && viewport.current)
      viewport.current.scrollTop = viewport.current.scrollHeight;
  }, [text, follow]);
  const manual = (offset?: number, prepend = false) =>
    void load(new AbortController().signal, offset, prepend);
  return (
    <div className="log-panel">
      <div className="pipeline-log-controls">
        {toolbar}
        <label>
          <input
            type="checkbox"
            checked={follow}
            onChange={(event) => setFollow(event.target.checked)}
          />
          {t("taskDetail.follow")}
        </label>
        <button
          className="secondary-button"
          disabled={!text}
          onClick={() => void clipboard.copy(text, "log")}
        >
          {t(clipboard.copied ? "taskDetail.copied" : "taskDetail.copy")}
        </button>
        <small>{formatBytes(range.size)}</small>
      </div>
      {range.earlier && !trimmed && text.length < MAX - LIMIT && (
        <button
          className="load-earlier"
          disabled={busy}
          onClick={() => manual(Math.max(0, range.start - LIMIT), true)}
        >
          {t("taskDetail.loadEarlier")}
        </button>
      )}
      {error && (
        <div className="error-state" role="alert">
          {error}
        </div>
      )}
      {!path ? (
        <p className="log-placeholder">
          {t(
            task.replica
              ? "replica.logUnavailable"
              : "taskDetail.logUnavailable",
          )}
        </p>
      ) : (
        <pre className="log-content" ref={viewport}>
          {text || t(busy ? "shell.loading" : "taskDetail.logEmpty")}
        </pre>
      )}
    </div>
  );
}
