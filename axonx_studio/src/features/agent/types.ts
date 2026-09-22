export interface AgentSessionInfo {
  session_id: string;
  summary: string;
  last_modified: number;
  file_size?: number | null;
  custom_title?: string | null;
  first_prompt?: string | null;
  git_branch?: string | null;
  cwd?: string | null;
  tag?: string | null;
  created_at?: number | null;
  backend: string;
}

export interface AgentSessionMessage {
  type: "user" | "assistant";
  uuid: string;
  session_id: string;
  message: Record<string, unknown>;
  parent_tool_use_id?: string | null;
  parent_agent_id?: string | null;
}

export type AgentBlockType = "thinking" | "text" | "tool" | "system" | "error";

export interface AgentHistoryBlock {
  block_id: string;
  block_type: AgentBlockType;
  message_uuid: string;
  role: "user" | "assistant" | "system";
  status: string;
  text: string;
  payload: Record<string, unknown>;
}

export interface AgentSession {
  info: AgentSessionInfo;
  messages: AgentSessionMessage[];
  blocks: AgentHistoryBlock[];
}

export interface AgentMutationResult {
  session_id: string;
}
