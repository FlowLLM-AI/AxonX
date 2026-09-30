import { axonx } from "../../shared/api/client";
import { streamJob, type JobEvent } from "../../shared/api/event";
import type {
  AgentMutationResult,
  AgentSession,
  AgentSessionInfo,
} from "./types";

export const listAgentSessions = (target?: string, signal?: AbortSignal) =>
  axonx.invoke<AgentSessionInfo[]>(
    "list_agent_sessions",
    { limit: 200, offset: 0 },
    { target, signal },
  );

export const getAgentSession = (
  sessionId: string,
  target?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<AgentSession>(
    "get_agent_session",
    { session_id: sessionId, limit: 1000, offset: 0 },
    { target, signal },
  );

export const streamAgentChat = (
  message: string,
  sessionId: string | undefined,
  target: string | undefined,
  signal: AbortSignal,
  onEvent: (event: JobEvent<unknown>) => void,
) =>
  streamJob<unknown>(
    axonx,
    "agent_chat",
    { message, ...(sessionId ? { session_id: sessionId } : {}) },
    { target, signal, onEvent },
  );

export const renameAgentSession = (
  sessionId: string,
  title: string,
  target?: string,
) =>
  axonx.invoke<AgentMutationResult>(
    "rename_agent_session",
    { session_id: sessionId, title },
    { target },
  );

export const tagAgentSession = (
  sessionId: string,
  tag: string | null,
  target?: string,
) =>
  axonx.invoke<AgentMutationResult>(
    "tag_agent_session",
    { session_id: sessionId, tag },
    { target },
  );

export const deleteAgentSession = (sessionId: string, target?: string) =>
  axonx.invoke<AgentMutationResult>(
    "delete_agent_session",
    { session_id: sessionId },
    { target },
  );

export const forkAgentSession = (sessionId: string, target?: string) =>
  axonx.invoke<AgentMutationResult>(
    "fork_agent_session",
    { session_id: sessionId },
    { target },
  );

export const cancelAgentTurn = (sessionId: string, target?: string) =>
  axonx.invoke<AgentMutationResult>(
    "cancel_agent_turn",
    { session_id: sessionId },
    { target },
  );
