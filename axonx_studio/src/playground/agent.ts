import type { AgentSession, AgentHistoryBlock } from "../features/agent/types";
import type { JobEvent } from "../shared/api/event";
import { sse } from "./stream";

export function createAgent() {
  const sessions = new Map<string, AgentSession>();
  const activeChats = new Map<string, AbortController>();
  let serial = 0;
  const block = (
    role: "user" | "assistant",
    text: string,
  ): AgentHistoryBlock => ({
    block_id: `block-${++serial}`,
    message_uuid: `message-${serial}`,
    block_type: "text",
    role,
    status: "completed",
    text,
    payload: {},
  });
  const makeSession = (prompt: string) => {
    const id = `demo-session-${++serial}`;
    const session: AgentSession = {
      info: {
        session_id: id,
        summary: prompt,
        first_prompt: prompt,
        backend: "playground",
        last_modified: Date.now(),
        created_at: Date.now(),
      },
      messages: [],
      blocks: [],
    };
    sessions.set(id, session);
    return session;
  };
  const initial = makeSession("Explain the demo backtest / 解释示例回测");
  initial.blocks.push(
    block("user", initial.info.summary),
    block(
      "assistant",
      "This is a scripted demonstration using fictional returns. Compare steady and volatile strategies in Strategy comparison. / 这是使用虚构收益的脚本演示。可以在策略比较中查看稳健与波动策略。",
    ),
  );

  const requiredSession = (args: Record<string, unknown>) => {
    const session = sessions.get(String(args.session_id));
    if (!session) throw new Error("Unknown demo session");
    return session;
  };
  const jobs: Record<string, (args: Record<string, unknown>) => unknown> = {
    list_agent_sessions: () =>
      [...sessions.values()].map((session) => session.info),
    get_agent_session: requiredSession,
    cancel_agent_turn: (args) => {
      const session = requiredSession(args);
      activeChats.get(session.info.session_id)?.abort();
      return { session_id: session.info.session_id };
    },
    rename_agent_session: (args) => {
      const session = requiredSession(args);
      session.info.custom_title = String(args.title);
      return { session_id: session.info.session_id };
    },
    tag_agent_session: (args) => {
      const session = requiredSession(args);
      session.info.tag = args.tag as string | null;
      return { session_id: session.info.session_id };
    },
    delete_agent_session: (args) => {
      const session = requiredSession(args);
      activeChats.get(session.info.session_id)?.abort();
      sessions.delete(session.info.session_id);
      return { session_id: session.info.session_id };
    },
    fork_agent_session: (args) => {
      const session = requiredSession(args);
      const copy = makeSession(session.info.summary);
      copy.blocks = structuredClone(session.blocks);
      return { session_id: copy.info.session_id };
    },
  };
  function stream(args: Record<string, unknown>, signal?: AbortSignal | null) {
    const sessionId = String(args.session_id || "");
    const session = sessionId
      ? sessions.get(sessionId)
      : makeSession(String(args.message));
    if (!session) throw new Error("Unknown demo session");
    if (activeChats.has(session.info.session_id))
      throw new Error("Demo turn already running");
    const stop = new AbortController();
    activeChats.set(session.info.session_id, stop);
    const user = block("user", String(args.message));
    const assistant = block("assistant", "");
    assistant.status = "running";
    const tool = block("assistant", "");
    tool.block_type = "tool";
    tool.message_uuid = assistant.message_uuid;
    tool.status = "running";
    tool.payload = {
      name: "Demo: inspect_backtests",
      input: { source: "synthetic fixtures" },
      status: "running",
    };
    session.blocks.push(user, tool, assistant);
    const zh = /[\u3400-\u9fff]/.test(String(args.message));
    const text = zh
      ? "这是脚本模拟对话，没有调用 LLM。示例包含稳健与波动两组回测；可在策略比较中检查净值、回撤和持仓。你也可以提交 playground.backtest，选择策略及成功或失败场景，查看执行日志。"
      : "This is a scripted conversation; no LLM is called. The demo includes steady and volatile backtests. Open Strategy comparison to inspect returns, drawdowns and holdings. Submit playground.backtest to choose a strategy and success or failure scenario, then follow its logs.";
    let offset = 0;
    let sequence = 0;
    const finish = () => {
      tool.status =
        stop.signal.aborted || signal?.aborted ? "cancelled" : "completed";
      tool.payload.status = tool.status;
      assistant.status = "completed";
      assistant.payload = { text: assistant.text, status: assistant.status };
      activeChats.delete(session.info.session_id);
      session.info.last_modified = Date.now();
    };
    return sse(
      () => {
        const events: JobEvent[] = [];
        const patches = [];
        tool.status =
          sequence === 0 && !stop.signal.aborted ? "running" : "completed";
        tool.payload = {
          ...tool.payload,
          status: tool.status,
          ...(tool.status === "completed"
            ? {
                result: { simulated: true, strategies: ["steady", "volatile"] },
              }
            : {}),
        };
        patches.push({
          operation: "replace" as const,
          block_id: tool.block_id,
          block_type: "tool" as const,
          delta: "",
          payload: { ...tool.payload, text: "" },
        });
        tool.payload.text = "";
        const delta = sequence === 0 ? "" : text.slice(offset, offset + 16);
        offset += delta.length;
        if (!stop.signal.aborted) assistant.text += delta;
        assistant.status =
          offset >= text.length || stop.signal.aborted
            ? "completed"
            : "running";
        assistant.payload = {
          text: assistant.text,
          status: assistant.status,
        };
        patches.push({
          operation: "replace" as const,
          block_id: assistant.block_id,
          block_type: "text" as const,
          delta: "",
          payload: assistant.payload,
        });
        events.push({
          kind: "agent_message",
          session_id: session.info.session_id,
          type_name: "AssistantMessage",
          message: { uuid: assistant.message_uuid },
          sequence: ++sequence,
          presentation: patches,
        });
        if (offset >= text.length || stop.signal.aborted) {
          finish();
          events.push({
            kind: "result",
            answer: { session_id: session.info.session_id },
            success: true,
            metadata: {
              terminal_reason: stop.signal.aborted
                ? "aborted_streaming"
                : "completed",
            },
          });
        }
        return events;
      },
      signal,
      finish,
    );
  }
  return { jobs, stream };
}
