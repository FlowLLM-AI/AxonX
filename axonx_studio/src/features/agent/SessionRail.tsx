import { GitFork, LoaderCircle, Pencil, Plus, Tag, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { RailResizer } from "../../shared/ui/RailResizer";
import type { AgentSessionInfo } from "./types";

interface SessionContextMenu {
  session: AgentSessionInfo;
  x: number;
  y: number;
}

function sessionTitle(session: AgentSessionInfo) {
  return (
    session.custom_title ||
    session.summary ||
    session.first_prompt ||
    session.session_id
  );
}

export function SessionRail({
  sessions,
  selectedId,
  loading,
  open,
  onClose,
  onNew,
  onSelect,
  onRename,
  onTag,
  onFork,
  onDelete,
}: {
  sessions: AgentSessionInfo[];
  selectedId?: string;
  loading: boolean;
  open: boolean;
  onClose: () => void;
  onNew: () => void;
  onSelect: (id: string) => void;
  onRename: (session: AgentSessionInfo) => void;
  onTag: (session: AgentSessionInfo) => void;
  onFork: (session: AgentSessionInfo) => void;
  onDelete: (session: AgentSessionInfo) => void;
}) {
  const { t, i18n } = useTranslation();
  const [contextMenu, setContextMenu] = useState<SessionContextMenu>();
  const contextMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!contextMenu) return;

    const closeOutside = (event: PointerEvent) => {
      if (!contextMenuRef.current?.contains(event.target as Node))
        setContextMenu(undefined);
    };
    const close = () => setContextMenu(undefined);
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };

    window.addEventListener("pointerdown", closeOutside);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("pointerdown", closeOutside);
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [contextMenu]);

  const runContextAction = (
    action: (session: AgentSessionInfo) => void,
  ) => {
    if (!contextMenu) return;
    const { session } = contextMenu;
    setContextMenu(undefined);
    action(session);
  };

  return (
    <>
      <aside className={`agent-session-rail ${open ? "open" : ""}`}>
        <header>
          <div>
            <strong>{t("agent.sessions")}</strong>
            <small>{sessions.length}</small>
          </div>
          <button
            aria-label={t("agent.newChat")}
            className="agent-new-session-button"
            onClick={onNew}
            title={t("agent.newChat")}
          >
            <Plus />
          </button>
        </header>
        <div className="agent-session-list">
          {loading && !sessions.length ? (
            <div className="agent-session-loading">
              <LoaderCircle className="spin" />
            </div>
          ) : !sessions.length ? (
            <p>{t("agent.noSessions")}</p>
          ) : (
            sessions.map((session) => {
              const selected = session.session_id === selectedId;
              return (
                <article
                  className={selected ? "selected" : ""}
                  key={session.session_id}
                  onContextMenu={(event) => {
                    event.preventDefault();
                    setContextMenu({
                      session,
                      x: Math.max(
                        8,
                        Math.min(event.clientX, window.innerWidth - 192),
                      ),
                      y: Math.max(
                        8,
                        Math.min(event.clientY, window.innerHeight - 176),
                      ),
                    });
                  }}
                >
                  <button
                    className="agent-session-main"
                    onClick={() => {
                      onSelect(session.session_id);
                      onClose();
                    }}
                  >
                    <strong>{sessionTitle(session)}</strong>
                    <span>
                      {session.tag && <i>{session.tag}</i>}
                      {new Intl.DateTimeFormat(i18n.resolvedLanguage, {
                        month: "short",
                        day: "numeric",
                      }).format(session.last_modified)}
                    </span>
                  </button>
                  {selected && (
                    <div className="agent-session-actions">
                      <button
                        onClick={() => onRename(session)}
                        title={t("agent.rename")}
                      >
                        <Pencil />
                      </button>
                      <button
                        onClick={() => onTag(session)}
                        title={t("agent.tag")}
                      >
                        <Tag />
                      </button>
                      <button
                        onClick={() => onFork(session)}
                        title={t("agent.fork")}
                      >
                        <GitFork />
                      </button>
                      <button
                        className="danger"
                        onClick={() => onDelete(session)}
                        title={t("agent.delete")}
                      >
                        <Trash2 />
                      </button>
                    </div>
                  )}
                </article>
              );
            })
          )}
        </div>
      </aside>
      <RailResizer min={220} max={480} className="agent-session-resizer" />
      {contextMenu && (
        <div
          aria-label={t("agent.sessionMenu")}
          className="agent-session-context-menu"
          ref={contextMenuRef}
          role="menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            onClick={() => runContextAction(onRename)}
            role="menuitem"
          >
            <Pencil />
            {t("agent.rename")}
          </button>
          <button onClick={() => runContextAction(onTag)} role="menuitem">
            <Tag />
            {t("agent.tag")}
          </button>
          <button onClick={() => runContextAction(onFork)} role="menuitem">
            <GitFork />
            {t("agent.fork")}
          </button>
          <button
            className="danger"
            onClick={() => runContextAction(onDelete)}
            role="menuitem"
          >
            <Trash2 />
            {t("agent.delete")}
          </button>
        </div>
      )}
      {open && (
        <button
          className="agent-rail-scrim"
          onClick={onClose}
          aria-label={t("agent.closeSessions")}
        />
      )}
    </>
  );
}
