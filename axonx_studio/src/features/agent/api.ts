import { axonx } from "../../shared/api/client";
import { streamJob, type JobEvent } from "../../shared/api/event";
import type {
  AgentMutationResult,
  AgentSession,
  AgentSessionInfo,
} from "./types";

export const listAgentSessions = (remoteIp?: string, signal?: AbortSignal) =>
  axonx.invoke<AgentSessionInfo[]>(
    "list_agent_sessions",
    { limit: 200, offset: 0 },
    { remoteIp, signal },
  );

export const getAgentSession = (
  sessionId: string,
  remoteIp?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<AgentSession>(
    "get_agent_session",
    { session_id: sessionId, limit: 1000, offset: 0 },
    { remoteIp, signal },
  );

export const streamAgentChat = (
  message: string,
  sessionId: string | undefined,
  remoteIp: string | undefined,
  signal: AbortSignal,
  onEvent: (event: JobEvent<unknown>) => void,
) =>
  streamJob<unknown>(
    axonx,
    "agent_chat",
    { message, ...(sessionId ? { session_id: sessionId } : {}) },
    { remoteIp, signal, onEvent },
  );

export const renameAgentSession = (
  sessionId: string,
  title: string,
  remoteIp?: string,
) =>
  axonx.invoke<AgentMutationResult>(
    "rename_agent_session",
    { session_id: sessionId, title },
    { remoteIp },
  );

export const tagAgentSession = (
  sessionId: string,
  tag: string | null,
  remoteIp?: string,
) =>
  axonx.invoke<AgentMutationResult>(
    "tag_agent_session",
    { session_id: sessionId, tag },
    { remoteIp },
  );

export const deleteAgentSession = (sessionId: string, remoteIp?: string) =>
  axonx.invoke<AgentMutationResult>(
    "delete_agent_session",
    { session_id: sessionId },
    { remoteIp },
  );

export const forkAgentSession = (sessionId: string, remoteIp?: string) =>
  axonx.invoke<AgentMutationResult>(
    "fork_agent_session",
    { session_id: sessionId },
    { remoteIp },
  );

export const cancelAgentTurn = (sessionId: string, remoteIp?: string) =>
  axonx.invoke<AgentMutationResult>(
    "cancel_agent_turn",
    { session_id: sessionId },
    { remoteIp },
  );
