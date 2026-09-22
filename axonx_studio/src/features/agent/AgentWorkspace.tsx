import { useCallback, useEffect, useRef, useState } from "react";
import { Menu } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ContextOption } from "../../app/types";
import type { AppRoute } from "../../app/routes";
import type {
  AgentMessageEvent,
  JobEvent,
  ResultEvent,
} from "../../shared/api/event";
import { isAbortError } from "../../shared/lib/errors";
import {
  cancelAgentTurn,
  deleteAgentSession,
  forkAgentSession,
  getAgentSession,
  listAgentSessions,
  renameAgentSession,
  streamAgentChat,
  tagAgentSession,
} from "./api";
import { Composer } from "./Composer";
import { Conversation } from "./Conversation";
import {
  applyAgentEvent,
  emptyConversation,
  fromHistory,
  optimisticUserBlock,
} from "./reducer";
import { SessionRail } from "./SessionRail";
import type { AgentSessionInfo } from "./types";
import { AxonXMark } from "./AxonXMark";

export function AgentWorkspace({
  view,
  resource,
  remoteIp,
  navigate,
  replace,
  onOptionsChange,
  onConnection,
}: {
  view: "new" | "chat" | "task";
  resource?: string;
  remoteIp?: string;
  navigate: (route: AppRoute) => void;
  replace: (route: AppRoute) => void;
  onOptionsChange: (options: ContextOption[]) => void;
  onConnection: (online: boolean) => void;
}) {
  const { t } = useTranslation();
  const sessionId = view === "chat" ? resource : undefined;
  const [sessions, setSessions] = useState<AgentSessionInfo[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [conversation, setConversation] = useState(emptyConversation);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [draft, setDraft] = useState("");
  const [running, setRunning] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState("");
  const [railOpen, setRailOpen] = useState(false);
  const activeSession = useRef<string | undefined>(sessionId);
  const controller = useRef<AbortController | null>(null);
  const runningRef = useRef(false);
  const taskStarted = useRef<string | undefined>(undefined);

  const refreshSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const result = await listAgentSessions(remoteIp);
      setSessions(result);
      onOptionsChange(
        result.map((session) => ({
          value: session.session_id,
          label:
            session.custom_title ||
            session.summary ||
            session.first_prompt ||
            session.session_id,
          detail: session.tag || session.backend,
        })),
      );
      onConnection(true);
    } catch (reason) {
      if (!isAbortError(reason)) {
        setError(reason instanceof Error ? reason.message : String(reason));
        onConnection(false);
      }
    } finally {
      setSessionsLoading(false);
    }
  }, [onConnection, onOptionsChange, remoteIp]);

  const reconcile = useCallback(
    async (id: string) => {
      const result = await getAgentSession(id, remoteIp);
      if (activeSession.current === id) {
        setConversation(fromHistory(result.blocks));
        setError("");
      }
      return result;
    },
    [remoteIp],
  );

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  useEffect(() => () => controller.current?.abort(), [remoteIp]);

  useEffect(() => {
    if (sessionId === activeSession.current && runningRef.current) return;
    if (runningRef.current && sessionId !== activeSession.current)
      controller.current?.abort();
    activeSession.current = sessionId;
    setError("");
    setDraft("");
    if (!sessionId) {
      setConversation(emptyConversation());
      setHistoryLoading(false);
      return;
    }
    const request = new AbortController();
    setHistoryLoading(true);
    getAgentSession(sessionId, remoteIp, request.signal)
      .then((result) => {
        if (activeSession.current === sessionId)
          setConversation(fromHistory(result.blocks));
        onConnection(true);
      })
      .catch((reason) => {
        if (isAbortError(reason)) return;
        setError(reason instanceof Error ? reason.message : String(reason));
        onConnection(false);
      })
      .finally(() => {
        if (activeSession.current === sessionId) setHistoryLoading(false);
      });
    return () => request.abort();
  }, [onConnection, remoteIp, sessionId]);

  const send = useCallback(
    async (provided?: string) => {
      const message = (provided ?? draft).trim();
      if (!message || runningRef.current) return;
      const requestedSession = activeSession.current;
      const localId = `local-${crypto.randomUUID()}`;
      setConversation((current) =>
        optimisticUserBlock(current, message, localId),
      );
      setDraft("");
      setError("");
      setRunning(true);
      runningRef.current = true;
      const streamController = new AbortController();
      controller.current = streamController;
      let resolvedSession = requestedSession;
      let terminalReason = "";
      const onEvent = (event: JobEvent<unknown>) => {
        if (event.kind === "agent_message") {
          const agentEvent = event as AgentMessageEvent;
          if (!resolvedSession) {
            resolvedSession = agentEvent.session_id;
            activeSession.current = resolvedSession;
            replace({
              section: "agent",
              view: "chat",
              resource: resolvedSession,
            });
          }
          setConversation((current) => applyAgentEvent(current, agentEvent));
        } else if (event.kind === "result") {
          const result = event as ResultEvent<unknown>;
          terminalReason =
            typeof result.metadata.terminal_reason === "string"
              ? result.metadata.terminal_reason
              : "";
        }
      };
      try {
        await streamAgentChat(
          message,
          requestedSession,
          remoteIp,
          streamController.signal,
          onEvent,
        );
        onConnection(true);
      } catch (reason) {
        if (!isAbortError(reason))
          setError(reason instanceof Error ? reason.message : String(reason));
      } finally {
        runningRef.current = false;
        setRunning(false);
        setStopping(false);
        controller.current = null;
        if (resolvedSession) {
          try {
            await reconcile(resolvedSession);
            await refreshSessions();
          } catch (reason) {
            if (!isAbortError(reason))
              setError(
                reason instanceof Error ? reason.message : String(reason),
              );
          }
        }
        if (
          terminalReason === "aborted_streaming" ||
          terminalReason === "aborted_tools"
        )
          setError(t("agent.cancelled"));
      }
    },
    [draft, onConnection, reconcile, refreshSessions, remoteIp, replace, t],
  );

  useEffect(() => {
    if (view !== "task" || !resource || taskStarted.current === resource)
      return;
    taskStarted.current = resource;
    const timer = window.setTimeout(
      () => void send(t("agent.taskPrompt", { taskId: resource })),
      0,
    );
    return () => window.clearTimeout(timer);
  }, [resource, send, t, view]);

  const stop = async () => {
    const id = activeSession.current;
    if (!id || stopping) return;
    setStopping(true);
    try {
      await cancelAgentTurn(id, remoteIp);
    } catch (reason) {
      setStopping(false);
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const rename = async (session: AgentSessionInfo) => {
    const title = window.prompt(
      t("agent.renamePrompt"),
      session.custom_title || "",
    );
    if (!title?.trim()) return;
    await renameAgentSession(session.session_id, title.trim(), remoteIp);
    await refreshSessions();
  };
  const tag = async (session: AgentSessionInfo) => {
    const value = window.prompt(t("agent.tagPrompt"), session.tag || "");
    if (value === null) return;
    await tagAgentSession(session.session_id, value.trim() || null, remoteIp);
    await refreshSessions();
  };
  const fork = async (session: AgentSessionInfo) => {
    const result = await forkAgentSession(session.session_id, remoteIp);
    await refreshSessions();
    navigate({ section: "agent", view: "chat", resource: result.session_id });
  };
  const remove = async (session: AgentSessionInfo) => {
    if (!window.confirm(t("agent.deleteConfirm"))) return;
    await deleteAgentSession(session.session_id, remoteIp);
    if (activeSession.current === session.session_id)
      navigate({ section: "agent", view: "new" });
    await refreshSessions();
  };

  return (
    <section className="agent-workspace">
      <SessionRail
        sessions={sessions}
        selectedId={sessionId}
        loading={sessionsLoading}
        open={railOpen}
        onClose={() => setRailOpen(false)}
        onNew={() => navigate({ section: "agent", view: "new" })}
        onSelect={(id) =>
          navigate({ section: "agent", view: "chat", resource: id })
        }
        onRename={(session) =>
          void rename(session).catch((reason) => setError(String(reason)))
        }
        onTag={(session) =>
          void tag(session).catch((reason) => setError(String(reason)))
        }
        onFork={(session) =>
          void fork(session).catch((reason) => setError(String(reason)))
        }
        onDelete={(session) =>
          void remove(session).catch((reason) => setError(String(reason)))
        }
      />
      <main className="agent-chat-pane">
        <header className="agent-chat-header">
          <button
            className="agent-mobile-sessions"
            onClick={() => setRailOpen(true)}
          >
            <Menu />
          </button>
          <div>
            <AxonXMark />
            <span>
              {sessionId ? t("agent.conversation") : t("agent.newChat")}
            </span>
          </div>
        </header>
        {error && (
          <div className="agent-error" role="alert">
            {error}
            <button onClick={() => setError("")}>×</button>
          </div>
        )}
        <Conversation
          conversation={conversation}
          loading={historyLoading}
          running={running}
        />
        <Composer
          value={draft}
          running={running}
          canStop={Boolean(activeSession.current) && !stopping}
          onChange={setDraft}
          onSend={() => void send()}
          onStop={() => void stop()}
        />
      </main>
    </section>
  );
}
