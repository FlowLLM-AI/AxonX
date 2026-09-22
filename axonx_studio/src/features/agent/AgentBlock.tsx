import { useEffect, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  CircleEllipsis,
  XCircle,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { DisplayBlock } from "./reducer";

function valueText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value == null) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function AgentBlock({
  block,
  latest = false,
}: {
  block: DisplayBlock;
  latest?: boolean;
}) {
  const [open, setOpen] = useState(latest);

  useEffect(() => {
    setOpen(latest);
  }, [latest]);

  if (block.block_type === "thinking") {
    return (
      <details
        className="agent-thinking"
        open={open}
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary>
          <CircleEllipsis />
          Thinking
          <ChevronDown />
        </summary>
        <div className="agent-markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {block.text}
          </ReactMarkdown>
        </div>
      </details>
    );
  }

  if (block.block_type === "tool") {
    const failed = block.status === "failed";
    const name = valueText(block.payload.name) || "Tool";
    return (
      <details
        className={`agent-tool ${failed ? "failed" : ""}`}
        open={open}
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary>
          {failed ? (
            <XCircle />
          ) : block.status === "running" ? (
            <CircleEllipsis />
          ) : (
            <CheckCircle2 />
          )}
          <strong>{name}</strong>
          <span className="agent-tool-status">{block.status}</span>
          <ChevronDown className="agent-tool-chevron" />
        </summary>
        <div>
          {block.payload.input != null && (
            <section>
              <small>INPUT</small>
              <pre>{valueText(block.payload.input)}</pre>
            </section>
          )}
          {block.payload.result != null && (
            <section>
              <small>RESULT</small>
              <pre>{valueText(block.payload.result)}</pre>
            </section>
          )}
        </div>
      </details>
    );
  }

  return (
    <div className={`agent-markdown agent-block-${block.block_type}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.text}</ReactMarkdown>
    </div>
  );
}
