import { useEffect, useMemo, useRef } from "react";
import { LoaderCircle, MessageSquareText } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ConversationState, DisplayBlock } from "./reducer";
import { AgentBlock } from "./AgentBlock";
import { AxonXMark } from "./AxonXMark";

interface MessageGroup {
  id: string;
  role: DisplayBlock["role"];
  blocks: DisplayBlock[];
}

export function Conversation({
  conversation,
  loading,
  running,
}: {
  conversation: ConversationState;
  loading: boolean;
  running: boolean;
}) {
  const { t } = useTranslation();
  const viewport = useRef<HTMLDivElement>(null);
  const groups = useMemo(() => {
    const result: MessageGroup[] = [];
    for (const id of conversation.order) {
      const block = conversation.blocks[id];
      if (!block) continue;
      const previous = result[result.length - 1];
      if (previous?.id === block.message_uuid) previous.blocks.push(block);
      else
        result.push({
          id: block.message_uuid,
          role: block.role,
          blocks: [block],
        });
    }
    return result;
  }, [conversation]);
  const latestBlockId = conversation.order.at(-1);

  useEffect(() => {
    if (viewport.current)
      viewport.current.scrollTop = viewport.current.scrollHeight;
  }, [conversation, running]);

  if (loading)
    return (
      <div className="agent-conversation-state">
        <LoaderCircle className="spin" />
        {t("agent.loadingConversation")}
      </div>
    );

  return (
    <div className="agent-conversation" ref={viewport}>
      {!groups.length && !running ? (
        <div className="agent-welcome">
          <span>
            <AxonXMark labelled />
          </span>
          <h1>{t("agent.welcomeTitle")}</h1>
          <p>{t("agent.welcomeLead")}</p>
        </div>
      ) : (
        <div className="agent-message-list">
          {groups.map((group) => (
            <article className={`agent-message ${group.role}`} key={group.id}>
              <header>
                {group.role === "user" ? <MessageSquareText /> : <AxonXMark />}
                <span>{t(`agent.roles.${group.role}`)}</span>
              </header>
              <div>
                {group.blocks.map((block) => (
                  <AgentBlock
                    block={block}
                    key={block.block_id}
                    latest={block.block_id === latestBlockId}
                  />
                ))}
              </div>
            </article>
          ))}
          {running && (
            <div className="agent-running-indicator" role="status">
              <i />
              <i />
              <i />
              <span>{t("agent.working")}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
