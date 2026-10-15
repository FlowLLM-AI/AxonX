import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AgentBlock } from "./AgentBlock";
import {
  applyAgentEvent,
  emptyConversation,
  type DisplayBlock,
} from "./reducer";

function block(overrides: Partial<DisplayBlock>): DisplayBlock {
  return {
    block_id: "block-1",
    block_type: "text",
    message_uuid: "message-1",
    role: "assistant",
    status: "completed",
    text: "",
    payload: {},
    ...overrides,
  };
}

describe("AgentBlock", () => {
  it("shows partial tool arguments, then complete input and results without a history reload", () => {
    let state = emptyConversation();
    const patch = (
      operation: "start" | "append" | "replace" | "finish",
      payload: Record<string, unknown>,
      delta = "",
    ) => {
      state = applyAgentEvent(state, {
        kind: "agent_message",
        session_id: "session-1",
        type_name: "StreamEvent",
        message_uuid: "message-1",
        role: "assistant",
        sequence: 0,
        presentation: [
          { operation, block_id: "tool-1", block_type: "tool", delta, payload },
        ],
      });
      return renderToStaticMarkup(
        <AgentBlock latest block={state.blocks["tool-1"]} />,
      );
    };

    patch("start", { name: "Bash", input: {}, status: "building_input" });
    const partial = patch("append", {}, '{"command": "echo ');
    expect(partial).toContain("echo ");
    expect(partial).not.toContain("<pre>{}</pre>");

    patch("append", {}, 'hello"}');
    expect(patch("replace", { status: "running" })).toContain("echo hello");
    const complete = patch("replace", {
      input: { command: "echo hello", description: "Print a greeting" },
      text: "",
    });
    expect(state.blocks["tool-1"].text).toBe("");
    expect(complete).toContain("Print a greeting");
    expect(complete).toContain("echo hello");

    const finished = patch("finish", { status: "succeeded", result: "hello" });
    expect(finished).toContain("echo hello");
    expect(finished).toContain("RESULT");
    expect(state.order).toEqual(["tool-1"]);
  });

  it("renders GFM tables as semantic markdown tables", () => {
    const html = renderToStaticMarkup(
      <AgentBlock
        block={block({
          text: "| Directory | Content |\n| --- | --- |\n| agent/ | Sessions |",
        })}
      />,
    );

    expect(html).toContain("<table>");
    expect(html).toContain("<th>Directory</th>");
    expect(html).toContain("<td>Sessions</td>");
  });

  it("renders tool status in the right-aligned status slot", () => {
    const html = renderToStaticMarkup(
      <AgentBlock
        block={block({
          block_type: "tool",
          status: "completed",
          payload: { name: "Bash" },
        })}
      />,
    );

    expect(html).toContain('class="agent-tool-status"');
    expect(html).toContain(">completed</span>");
  });

  it("opens the latest collapsible block", () => {
    const thinking = renderToStaticMarkup(
      <AgentBlock
        latest
        block={block({ block_type: "thinking", text: "Inspecting files" })}
      />,
    );
    const tool = renderToStaticMarkup(
      <AgentBlock
        latest
        block={block({ block_type: "tool", payload: { name: "Bash" } })}
      />,
    );

    expect(thinking).toContain('<details class="agent-thinking" open="">');
    expect(tool).toContain('<details class="agent-tool " open="">');
  });
});
