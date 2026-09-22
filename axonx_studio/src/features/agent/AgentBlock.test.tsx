import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AgentBlock } from "./AgentBlock";
import type { DisplayBlock } from "./reducer";

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
