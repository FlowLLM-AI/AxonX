import { axonx, type RequestOptions } from "../../shared/api/client";
import type {
  AgentMutationResult,
  AgentSession,
  AgentSessionInfo,
} from "../../shared/api/contracts";
import type { StreamOptions } from "../../shared/api/event";

export const listAgentSessions = (options: RequestOptions = {}) =>
  axonx.invoke<AgentSessionInfo[]>(
    "list_agent_sessions",
    { limit: 200, offset: 0 },
    options,
  );

export const getAgentSession = (
  sessionId: string,
  options: RequestOptions = {},
) =>
  axonx.invoke<AgentSession>(
    "get_agent_session",
    { session_id: sessionId, limit: 1000, offset: 0 },
    options,
  );

export const streamAgentChat = (
  arguments_: { message: string; session_id?: string },
  options: StreamOptions<unknown> = {},
) => axonx.stream("agent_chat", arguments_, options);

export const renameAgentSession = (
  sessionId: string,
  title: string,
  options: RequestOptions = {},
) =>
  axonx.invoke<AgentMutationResult>(
    "rename_agent_session",
    { session_id: sessionId, title },
    options,
  );

export const tagAgentSession = (
  sessionId: string,
  tag: string | null,
  options: RequestOptions = {},
) =>
  axonx.invoke<AgentMutationResult>(
    "tag_agent_session",
    { session_id: sessionId, tag },
    options,
  );

export const deleteAgentSession = (
  sessionId: string,
  options: RequestOptions = {},
) =>
  axonx.invoke<AgentMutationResult>(
    "delete_agent_session",
    { session_id: sessionId },
    options,
  );

export const forkAgentSession = (
  sessionId: string,
  options: RequestOptions = {},
) =>
  axonx.invoke<AgentMutationResult>(
    "fork_agent_session",
    { session_id: sessionId },
    options,
  );

export const cancelAgentTurn = (
  sessionId: string,
  options: RequestOptions = {},
) =>
  axonx.invoke<AgentMutationResult>(
    "cancel_agent_turn",
    { session_id: sessionId },
    options,
  );
