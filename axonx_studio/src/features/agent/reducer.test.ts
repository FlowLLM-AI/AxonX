import { describe, expect, it } from "vitest";
import type { AgentMessageEvent } from "../../shared/api/event";
import {
  applyAgentEvent,
  emptyConversation,
  fromHistory,
  optimisticUserBlock,
} from "./reducer";

function event(
  sequence: number,
  presentation: AgentMessageEvent["presentation"],
): AgentMessageEvent {
  return {
    kind: "agent_message",
    session_id: "session-1",
    type_name: "StreamEvent",
    message: { uuid: "message-1" },
    sequence,
    presentation,
  };
}

describe("agent conversation reducer", () => {
  it("merges streamed text patches into one assistant block", () => {
    let state = applyAgentEvent(
      emptyConversation(),
      event(0, [
        {
          operation: "start",
          block_id: "message-1:0",
          block_type: "text",
          delta: "",
          payload: {},
        },
      ]),
    );
    state = applyAgentEvent(
      state,
      event(1, [
        {
          operation: "append",
          block_id: "message-1:0",
          block_type: "text",
          delta: "Hello",
          payload: {},
        },
        {
          operation: "finish",
          block_id: "message-1:0",
          block_type: "text",
          delta: "",
          payload: {},
        },
      ]),
    );

    expect(state.order).toEqual(["message-1:0"]);
    expect(state.blocks["message-1:0"]).toMatchObject({
      role: "assistant",
      message_uuid: "message-1",
      text: "Hello",
      status: "completed",
    });
  });

  it("finishes an existing tool without changing its message ownership", () => {
    let state = applyAgentEvent(
      emptyConversation(),
      event(0, [
        {
          operation: "start",
          block_id: "tool-1",
          block_type: "tool",
          delta: "",
          payload: { name: "status", status: "running" },
        },
      ]),
    );
    state = applyAgentEvent(state, {
      ...event(1, [
        {
          operation: "finish",
          block_id: "tool-1",
          block_type: "tool",
          delta: "",
          payload: { result: "ok", status: "succeeded" },
        },
      ]),
      type_name: "UserMessage",
      message: { uuid: "tool-result-message" },
    });

    expect(state.blocks["tool-1"]).toMatchObject({
      role: "assistant",
      message_uuid: "message-1",
      status: "succeeded",
      payload: { name: "status", result: "ok" },
    });
  });

  it("replaces optimistic state with authoritative history", () => {
    const optimistic = optimisticUserBlock(
      emptyConversation(),
      "hello",
      "local-1",
    );
    expect(optimistic.blocks["local-1"].local).toBe(true);

    const restored = fromHistory([
      {
        block_id: "stored-1",
        block_type: "text",
        message_uuid: "user-1",
        role: "user",
        status: "completed",
        text: "hello",
        payload: {},
      },
    ]);
    expect(restored.order).toEqual(["stored-1"]);
    expect(restored.blocks["local-1"]).toBeUndefined();
  });
});
