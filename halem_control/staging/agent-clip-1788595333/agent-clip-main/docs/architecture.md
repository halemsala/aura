# Architecture

## Overview

Agent Clip is an AI agent that runs as a Pinix Clip. It receives messages via `commands/send`, executes an agentic loop (LLM + tool calls), and persists conversations in SQLite.

```
Clip Dock / CLI
  │ ClipService.Invoke("send", stdin)
  ▼
commands/send → bin/agent send
  │
  ├── BuildContext()         Load history, build system prompt
  ├── RunLoop()              LLM → tool_calls → execute → repeat
  ├── SaveMessages()         Persist to SQLite
  └── ProcessMemory()        Generate summary + embedding (background)
```

## Process Model

**Process-per-invocation**: Each `send` starts a fresh process, loads state from SQLite, runs the agentic loop, saves results, and exits. No daemon, no session cache.

This simplifies deployment (no process management) at the cost of cold-start context rebuilding. The Run Window mechanism (see [context.md](context.md)) mitigates this by only loading recent Runs as full messages.

### Async Mode

`send --async` spawns a detached background process (`_run-worker`). The foreground returns immediately with a run_id. The worker:

1. Loads context from DB
2. Runs the agentic loop (output → file, not stdout)
3. Checks inbox between LLM calls (for injected messages)
4. Saves messages and generates memory on completion

## Data Flow

```
send -p "hello" -t <topic>
  │
  ├─ OpenDB()
  ├─ GetActiveRun() → defense check
  ├─ CreateRun() → register in runs table
  │
  ├─ BuildContext()
  │   ├─ System prompt: base + facts
  │   ├─ Topic history: old Run summaries
  │   ├─ Recent Runs: full messages (3-7)
  │   └─ User message: <user> + <recall> + <environment>
  │
  ├─ RunLoop()
  │   ├─ CallLLM() with tools
  │   ├─ If tool_calls → execute via Registry → append results → loop
  │   ├─ If stop → TryFinishRun() (atomic inbox check)
  │   │   ├─ inbox has messages → continue loop
  │   │   └─ inbox empty → mark done
  │   └─ Return newMsgs
  │
  ├─ SaveMessages(topicID, runID, newMsgs)
  │
  └─ ProcessMemory() (background process)
      ├─ GenerateSummary() → LLM call
      ├─ GetEmbedding() → OpenRouter API
      └─ StoreSummary() → SQLite
```

## Component Diagram

```
┌─────────────────────────────────────────────────────┐
│                    cmd/agent/main.go                  │
│  sendCmd, createTopicCmd, workerCmd, getRunCmd, ...  │
└────────────────┬────────────────────────────────────┘
                 │
    ┌────────────┼─────────────────────┐
    │            │                     │
    ▼            ▼                     ▼
┌────────┐ ┌──────────┐         ┌──────────┐
│context │ │  loop    │         │  output  │
│.go     │ │  .go     │         │  .go     │
│        │ │          │         │          │
│Build   │ │RunLoop   │         │CLIOutput │
│Context │ │          │◄────────│JSONLOut  │
└───┬────┘ └────┬─────┘         └──────────┘
    │           │
    │     ┌─────┼──────────┐
    │     │     │          │
    ▼     ▼     ▼          ▼
┌──────┐ ┌───────┐  ┌──────────┐
│memory│ │tools  │  │  chain   │
│.go   │ │.go    │  │  .go     │
│      │ │       │  │          │
│Search│ │Registry│  │ParseChain│
│Facts │ │Builtins│  │&&, ;, | │
└──┬───┘ └───┬───┘  └──────────┘
   │         │
   │    ┌────┼────┐
   │    │         │
   ▼    ▼         ▼
┌──────┐  ┌──────────┐
│embed │  │  clip    │
│.go   │  │  .go     │
│      │  │          │
│OpenAI│  │InvokeClip│
│API   │  │(pinix)   │
└──────┘  └──────────┘
   │
   ▼
┌──────────────┐    ┌──────────┐
│   db.go      │    │  run.go  │
│              │    │          │
│ Topics       │    │ Create   │
│ Messages     │    │ Finish   │
│ SaveMessages │    │ Inject   │
│ LoadByRunID  │    │ Inbox    │
└──────┬───────┘    └────┬─────┘
       │                 │
       ▼                 ▼
   ┌─────────────────────────┐
   │      SQLite (WAL)       │
   │  topics, messages, runs │
   │  run_inbox, summaries   │
   │  summaries_fts, facts   │
   └─────────────────────────┘
```
