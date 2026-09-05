# Memory System

## Overview

The memory system gives the agent persistent recall across topics and sessions. It has three layers:

```
┌─────────────────────────────┐
│  Facts (permanent)          │  "user's birthday is March 15"
│  Stored via memory store    │  Always in system prompt
├─────────────────────────────┤
│  Summaries + Embeddings     │  Generated after each Run
│  Per-Run, with OpenRouter   │  Used for semantic search
│  embedding (1536d)          │
├─────────────────────────────┤
│  Topic Messages (session)   │  Full message history
│  Loaded via Run Window      │  Direct LLM context
└─────────────────────────────┘
```

## Write Path

After each Run completes, a background process generates memory:

```
Run finishes → SaveMessages() → spawn _process-memory
                                  │
                                  ├─ GenerateSummary()
                                  │   LLM call with full Run trajectory
                                  │   + recent 5 summaries as context
                                  │   → 1-3 sentence summary
                                  │
                                  ├─ GetEmbedding()
                                  │   OpenRouter text-embedding-3-small
                                  │   → float32[1536]
                                  │
                                  └─ StoreSummary()
                                      topic_id, run_id, summary, embedding → SQLite
```

### Summary Generation

The full Run trajectory is rendered and sent to the LLM:

```
[user] <user>message</user><environment>...</environment>
[tool_call] run({"command":"clip sandbox bash ls"})
[tool_result] file1\nfile2\nfile3
[assistant] Here are the files...
```

Recent 5 summaries are included as context so the LLM knows what came before.

### Background Processing

Memory is processed in a detached subprocess (`_process-memory`) so the user doesn't wait. The process reads messages from the DB by `run_id`, generates the summary, embeds it, and stores it.

## Read Path

### Auto-injection (every Run)

`BuildContext()` automatically injects memory into the LLM context:

1. **Facts** → system prompt (`## Known Facts`)
2. **Semantic search** → `<recall>` tag in user message

### Semantic Search

```
User message "help me with Go channels"
  │
  ├─ GetEmbedding("help me with Go channels")
  │   → float32[1536]
  │
  ├─ Load ALL summary embeddings from SQLite
  │
  ├─ Compute cosine similarity for each
  │   Threshold: ≥ 0.5 (50%)
  │
  ├─ Sort by similarity, take top 3
  │
  └─ Format as <recall> block
      [03-09 14:20] (72%) topic="Go讨论" run=a1b2
        用户之前讨论过 Go 的并发模型...
```

### Keyword Search (FTS5)

SQLite FTS5 provides keyword-based search as a fallback/supplement:

```sql
SELECT * FROM summaries_fts WHERE summaries_fts MATCH 'database schema'
```

Used when semantic search returns fewer than `limit` results.

## Search Commands

### memory search

Cross-topic search with optional filters:

```bash
memory search <query>                # all topics, semantic + keyword
memory search <query> -t <topic-id>  # within a specific topic
memory search <query> -k <keyword>   # post-filter by keyword
```

Results include topic name and run_id for drill-down:

```
Found 3 results:
  [03-09 15:04] (72%) topic="Go讨论" run=a1b2c3
    用户讨论了数据库schema设计...
  [03-08 10:20] (65%) topic="项目规划" run=d4e5f6
    讨论了项目架构和技术选型...
```

### topic search

Search within a specific topic's runs:

```bash
topic search <topic-id> <query>
```

Same underlying search engine, scoped to one topic.

### Progressive Disclosure

```
memory search "database"           → find relevant topics/runs
  ↓ found run=a1b2c3
topic run a1b2c3                   → see full messages
  ↓ or
topic search <topic-id> "schema"   → find more in same topic
```

## Facts

Persistent knowledge stored by the LLM:

```bash
memory store "user's birthday is March 15"    # LLM calls this
memory facts                                    # list all
memory forget 3                                 # delete by ID
```

Facts are always in the system prompt → available in every conversation, every topic.

## Database Schema

```sql
-- Per-Run summary with embedding
summaries (id, topic_id, run_id, summary, user_message, embedding BLOB, created_at)

-- FTS5 index (auto-synced via trigger)
summaries_fts (summary, user_message)

-- Persistent facts
facts (id, content, category, created_at)
```

## Embedding Storage

Embeddings are stored as raw bytes (BLOB) in SQLite, not using vec0:

```go
// Encode: float32[] → []byte (little-endian)
func EncodeEmbedding(v []float32) []byte

// Decode: []byte → float32[]
func DecodeEmbedding(b []byte) []float32

// Search: load all embeddings, compute cosine similarity in Go
func SearchMemorySemantic(db, queryEmbedding, limit) []Summary
```

This is O(n) per search but fast for typical dataset sizes (thousands of summaries). No CGO dependency.
