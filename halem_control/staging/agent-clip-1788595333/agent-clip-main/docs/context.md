# Context Management

## Problem

Each `send` is a fresh process. We need to rebuild the LLM context from the database. Loading ALL messages from a long-running topic would explode the context window.

## Run Window (3→7)

The Run Window controls how many Runs are loaded as full messages vs summaries.

### Growth Cycle

```
Run 1:  window = [1]                         1 full
Run 2:  window = [1,2]                       2 full
Run 3:  window = [1,2,3]                     3 full
...
Run 7:  window = [1,2,3,4,5,6,7]             7 full (max)
Run 8:  COMPRESS → window = [6,7,8]          3 full, 1-5 as summaries
Run 9:  window = [6,7,8,9]                   4 full (growing again)
...
Run 12: window = [6,7,8,9,10,11,12]          7 full (max again)
Run 13: COMPRESS → window = [11,12,13]       3 full
```

- **RunWindowMin = 3**: minimum full Runs after compression
- **RunWindowMax = 7**: maximum before compression triggers

### Why 3→7?

Between compressions (every ~5 turns), the message prefix is stable — older Runs' messages don't change. This enables **~80% prompt cache hit rate**.

At compression boundaries (every 5th turn), the prefix changes → cache miss. But it's only 1 in 5 turns.

## Message Array Structure

Optimized for prompt cache — stable content at the top, dynamic at the bottom.

```
[system: base prompt + facts]              ← STABLE (only changes when facts change)

[user: "以下是之前的对话摘要：             ← SEMI-STABLE (changes at compression boundary)
  - [14:20] 用户问了X，agent做了Y
  - [14:35] 用户问了A，结果是B
  ..."]
[assistant: "了解"]                        ← STABLE

[Run N-2 messages: user, assistant, tool...] ← STABLE (finished Runs don't change)
[Run N-1 messages: user, assistant, tool...] ← STABLE
[Run N messages: user, assistant, tool...]   ← STABLE

[user: <user>new message</user>            ← DYNAMIC (changes every turn)
       <recall>semantic search</recall>
       <environment>time, clips</environment>]
```

### Prompt Cache Hit Pattern

| Turn | What changes | Cache |
|------|-------------|-------|
| 4 (after compress) | system + history + 3 runs | MISS |
| 5 | + 1 new run at end | HIT (prefix same) |
| 6 | + 1 new run at end | HIT |
| 7 | + 1 new run at end | HIT |
| 8 | + 1 new run at end | HIT |
| 9 (compress) | system + new history + 3 runs | MISS |
| 10 | + 1 new run at end | HIT |

## XML User Message

The final user message uses XML tags to separate user input from system-injected context:

```xml
<user>
actual user message (what the human typed)
</user>

<recall>
- [03-09 15:04] (72%) topic="Go讨论" run=a1b2c3
  用户讨论了数据库schema设计...
- [03-08 10:20] (65%) topic="项目规划" run=d4e5f6
  讨论了项目架构和技术选型...
</recall>

<environment>
<time>2026-03-09 15:30:00 CST</time>
<clips>
  <clip name="sandbox" commands="bash, read, write, edit" />
</clips>
</environment>
```

- `<user>`: distinguishes human input from injected context
- `<recall>`: semantic search results from memory (cross-topic)
- `<environment>`: current state (time, available clips)

Future: `<webhook>`, `<event>` tags for non-user triggers.

## System Prompt

The system prompt is deliberately minimal and stable:

```
base prompt (personality, rules)
+ ## Known Facts (from facts table)
```

What's NOT in the system prompt:
- Recent summaries → in topic history block (user message)
- Semantic search → in `<recall>` tag (user message)
- Available commands → in `run` tool description (tool definition)

This keeps the system prompt cacheable across turns.

## Implementation

### BuildContext (internal/context.go)

```go
func BuildContext(db, cfg, topicID, userMessage) (*ContextResult, error)
```

1. Build system prompt: base + facts
2. Get completed Runs for topic
3. If ≤7: all as full messages. If >7: last 3 full, rest as summaries
4. Assemble: [topic history] + ["了解"] + [full Run messages] + [wrapped user message]

### wrapUserMessage

```go
func wrapUserMessage(cfg, db, userMessage) Message
```

1. Wrap user text in `<user>` tags
2. Run semantic search → format as `<recall>`
3. Build `<environment>` (time, clips)
4. Combine into a single user Message
