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
      blocks.map((block) => {
        const { text: _text, status: _status, ...payload } = block.payload;
        void _text;
        void _status;
        return [block.block_id, { ...block, payload }];
      }),
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
  const {
    text: replacementText,
    status: replacementStatus,
    ...details
  } = patch.payload;
  const payload = { ...created.payload, ...details };
  let text = created.text;
  if (patch.operation === "append") text += patch.delta;
  if (patch.operation === "replace" && typeof replacementText === "string")
    text = replacementText;
  const status =
    typeof replacementStatus === "string"
      ? replacementStatus
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
  const { role, message_uuid: messageUuid } = event;
  return event.presentation.reduce(
    (current, patch) => applyPatch(current, patch, role, messageUuid),
    state,
  );
}
