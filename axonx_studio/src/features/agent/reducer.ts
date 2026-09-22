import type {
  AgentBlockPatch,
  AgentMessageEvent,
} from "../../shared/api/event";
import type { AgentHistoryBlock } from "./types";

export interface DisplayBlock extends AgentHistoryBlock {
  local?: boolean;
}

export interface ConversationState {
  order: string[];
  blocks: Record<string, DisplayBlock>;
}

export const emptyConversation = (): ConversationState => ({
  order: [],
  blocks: {},
});

export function fromHistory(blocks: AgentHistoryBlock[]): ConversationState {
  return {
    order: blocks.map((block) => block.block_id),
    blocks: Object.fromEntries(
      blocks.map((block) => [block.block_id, { ...block }]),
    ),
  };
}

export function optimisticUserBlock(
  state: ConversationState,
  text: string,
  id: string,
): ConversationState {
  const block: DisplayBlock = {
    block_id: id,
    block_type: "text",
    message_uuid: id,
    role: "user",
    status: "completed",
    text,
    payload: {},
    local: true,
  };
  return {
    order: [...state.order, id],
    blocks: { ...state.blocks, [id]: block },
  };
}

function stringField(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

function eventIdentity(event: AgentMessageEvent) {
  const role =
    event.type_name === "UserMessage"
      ? "user"
      : event.type_name === "AssistantMessage" ||
          event.type_name === "StreamEvent"
        ? "assistant"
        : "system";
  return {
    role: role as DisplayBlock["role"],
    messageUuid:
      stringField(event.message.uuid) ||
      stringField(event.message.message_id) ||
      `${event.session_id}:${event.sequence}`,
  };
}

function applyPatch(
  state: ConversationState,
  patch: AgentBlockPatch,
  role: DisplayBlock["role"],
  messageUuid: string,
): ConversationState {
  const existing = state.blocks[patch.block_id];
  const created: DisplayBlock = existing || {
    block_id: patch.block_id,
    block_type: patch.block_type,
    message_uuid: messageUuid,
    role,
    status: "running",
    text: "",
    payload: {},
  };
  const payload = { ...created.payload, ...patch.payload };
  let text = created.text;
  if (patch.operation === "append") text += patch.delta;
  if (patch.operation === "replace" && typeof patch.payload.text === "string")
    text = patch.payload.text;
  const status =
    typeof patch.payload.status === "string"
      ? patch.payload.status
      : patch.operation === "finish"
        ? "completed"
        : created.status;
  const block: DisplayBlock = {
    ...created,
    block_type: patch.block_type,
    status,
    text,
    payload,
  };
  return {
    order: existing ? state.order : [...state.order, patch.block_id],
    blocks: { ...state.blocks, [patch.block_id]: block },
  };
}

export function applyAgentEvent(
  state: ConversationState,
  event: AgentMessageEvent,
): ConversationState {
  const { role, messageUuid } = eventIdentity(event);
  return event.presentation.reduce(
    (current, patch) => applyPatch(current, patch, role, messageUuid),
    state,
  );
}
