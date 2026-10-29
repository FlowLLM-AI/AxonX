# Agent Session API

Sessions are owned by the configured Agent backend and persisted in its session store. Keep actual backend session UUIDs.

Use the [HTTP/MCP protocol](overview.md) and discover schemas with `axonx help --job NAME`. Replace example Task/session IDs with actual values.

## Endpoint list

| Job                    | Purpose                                                           |
| ---------------------- | ----------------------------------------------------------------- |
| `agent_chat`           | Run one interactive Agent session turn over the workspace.        |
| `list_agent_sessions`  | List Agent Sessions for this workspace, newest first.             |
| `get_agent_session`    | Return one Agent Session and its visible message history.         |
| `rename_agent_session` | Set the custom title of an Agent Session.                         |
| `tag_agent_session`    | Set or clear an Agent Session tag.                                |
| `delete_agent_session` | Permanently delete an Agent Session and its subagent transcripts. |
| `fork_agent_session`   | Fork an Agent Session, optionally at one message UUID.            |
| `cancel_agent_turn`    | Interrupt the running turn in an Agent Session.                   |

## agent_chat

Run one interactive Agent session turn over the workspace.

| Argument     | Type     | Required | Default / constraints                                                                                      |
| ------------ | -------- | -------- | ---------------------------------------------------------------------------------------------------------- |
| `message`    | `string` | yes      | `{"minLength":1}`                                                                                          |
| `session_id` | `string` | no       | `{"pattern":"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"}` |

```json
{
  "arguments": {
    "message": "Inspect the workspace and summarize available evidence"
  }
}
```

Omitting session_id creates a session; supplying one resumes stored context. Prefer SSE for presentation patches. A model turn and a research process have separate lifecycles.

## list_agent_sessions

List Agent Sessions for this workspace, newest first.

| Argument | Type      | Required | Default / constraints         |
| -------- | --------- | -------- | ----------------------------- |
| `limit`  | `integer` | no       | `{"minimum":1,"maximum":200}` |
| `offset` | `integer` | no       | `{"minimum":0,"default":0}`   |

```json
{
  "arguments": {
    "limit": 20,
    "offset": 0
  }
}
```

## get_agent_session

Return one Agent Session and its visible message history.

| Argument     | Type      | Required | Default / constraints                                                                                      |
| ------------ | --------- | -------- | ---------------------------------------------------------------------------------------------------------- |
| `session_id` | `string`  | yes      | `{"pattern":"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"}` |
| `limit`      | `integer` | no       | `{"minimum":1,"maximum":1000}`                                                                             |
| `offset`     | `integer` | no       | `{"minimum":0,"default":0}`                                                                                |

```json
{
  "arguments": {
    "session_id": "01234567-89ab-4cde-8f01-23456789abcd",
    "limit": 20
  }
}
```

## rename_agent_session

Set the custom title of an Agent Session.

| Argument     | Type     | Required | Default / constraints                                                                                      |
| ------------ | -------- | -------- | ---------------------------------------------------------------------------------------------------------- |
| `session_id` | `string` | yes      | `{"pattern":"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"}` |
| `title`      | `string` | yes      | `{"minLength":1}`                                                                                          |

```json
{
  "arguments": {
    "session_id": "01234567-89ab-4cde-8f01-23456789abcd",
    "title": "Research"
  }
}
```

## tag_agent_session

Set or clear an Agent Session tag.

| Argument     | Type                 | Required | Default / constraints                                                                                      |
| ------------ | -------------------- | -------- | ---------------------------------------------------------------------------------------------------------- |
| `session_id` | `string`             | yes      | `{"pattern":"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"}` |
| `tag`        | `['string', 'null']` | yes      | `—`                                                                                                        |

```json
{
  "arguments": {
    "session_id": "01234567-89ab-4cde-8f01-23456789abcd",
    "tag": "research"
  }
}
```

## delete_agent_session

Permanently delete an Agent Session and its subagent transcripts.

| Argument     | Type     | Required | Default / constraints                                                                                      |
| ------------ | -------- | -------- | ---------------------------------------------------------------------------------------------------------- |
| `session_id` | `string` | yes      | `{"pattern":"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"}` |

```json
{
  "arguments": {
    "session_id": "01234567-89ab-4cde-8f01-23456789abcd"
  }
}
```

## fork_agent_session

Fork an Agent Session, optionally at one message UUID.

| Argument           | Type     | Required | Default / constraints                                                                                      |
| ------------------ | -------- | -------- | ---------------------------------------------------------------------------------------------------------- |
| `session_id`       | `string` | yes      | `{"pattern":"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"}` |
| `up_to_message_id` | `string` | no       | `{"pattern":"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"}` |
| `title`            | `string` | no       | `{"minLength":1}`                                                                                          |

```json
{
  "arguments": {
    "session_id": "01234567-89ab-4cde-8f01-23456789abcd"
  }
}
```

## cancel_agent_turn

Interrupt the running turn in an Agent Session.

| Argument     | Type     | Required | Default / constraints                                                                                      |
| ------------ | -------- | -------- | ---------------------------------------------------------------------------------------------------------- |
| `session_id` | `string` | yes      | `{"pattern":"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"}` |

```json
{
  "arguments": {
    "session_id": "01234567-89ab-4cde-8f01-23456789abcd"
  }
}
```

Interrupts the active model turn for this session. It is not a Task termination API; use target-side CLI kill for a research execution.

## Session evidence

Lists/history have offset and optional limit bounds. Forking returns a separate stored session; deletion is permanent and includes subagent transcripts. A resumed turn uses stored context. Inspect the final result and presentation events, and inspect Task records independently for any research started during the turn. See [Events](events.md) and [Agent usage](../agent/usage.md).

Source: [Default Job contracts](../../../axonx/app/config/default.yaml) · [Job protocol](overview.md)
