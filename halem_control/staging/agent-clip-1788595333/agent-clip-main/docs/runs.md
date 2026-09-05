# Runs & Async Execution

## What is a Run?

A Run is one complete agentic loop cycle:

```
User message arrives (send -p "...")
  │
  ├─ LLM call (streaming)
  │   ├─ finish_reason: "tool_calls" → execute tools → call LLM again (same Run)
  │   └─ finish_reason: "stop" → Run ends
  │
  └─ Run complete: messages saved, summary generated
```

A Run starts when a message is sent and ends when the LLM produces a final text response. Multiple tool call rounds belong to the same Run.

## Run Lifecycle

```
            ┌──────────┐
   send -p  │          │
   ────────►│ running  │
            │          │
            └────┬─────┘
                 │
        ┌────────┼────────┐
        │        │        │
        ▼        ▼        ▼
   ┌────────┐ ┌───────┐ ┌───────────┐
   │  done  │ │ error │ │ cancelled │
   └────────┘ └───────┘ └───────────┘
```

States:
- **running**: agentic loop in progress
- **done**: LLM returned `finish_reason: "stop"`, messages saved
- **error**: LLM error, process crash, or unrecoverable failure
- **cancelled**: user called `cancel-run`

## Sync vs Async

### Sync (default)

```bash
commands/send -p "hello"
```

- Blocks until Run completes
- LLM tokens stream to stdout
- Process exits after save + memory processing

### Async

```bash
commands/send -p "complex task" --async
# → [run] a1b2c3 started (async, pid 12345)
```

- Returns immediately with run_id
- Background worker process runs the loop
- Output written to `data/runs/<run-id>/output`
- Check progress: `commands/get-run a1b2c3`

## Message Injection

Send additional context to a running Run:

```bash
commands/send -p "also check file X" -r a1b2c3
```

### How it works

1. Inject process: SQLite transaction — verify run is `running`, insert into `run_inbox`
2. Run process: checks inbox at two points:
   - Top of each loop iteration (between tool calls)
   - Atomic finish check (`TryFinishRun`)

### Atomic Finish (no message loss)

When the LLM returns `finish_reason: "stop"`:

```sql
BEGIN EXCLUSIVE;
  SELECT * FROM run_inbox WHERE run_id = ?;
  -- If messages found: DELETE them, COMMIT → continue loop
  -- If empty: UPDATE runs SET status='done', COMMIT → exit
```

This prevents the race condition where an inject arrives between the last inbox check and the Run finishing.

### All injection timing scenarios

| When inject arrives | Result |
|--------------------|--------|
| Between tool calls | Read at next iteration → LLM sees it |
| During LLM streaming → then tool_calls | Next iteration reads it |
| During LLM streaming → then stop | Atomic finish reads it → continues |
| Exact same moment as finish | SQLite transaction: one wins, no loss |
| After Run finished | Error: "run is not active (status: done)" |

## Defense: One Run Per Topic

A topic can only have one active Run at a time. If you `send -t <topic>` while a Run is active:

```
Error: topic abc has an active run (xyz, running 14s)
  → inject:  send -p '...' -r xyz
  → watch:   get-run xyz
  → cancel:  cancel-run xyz
```

This prevents concurrent Runs from corrupting conversation context.

### Stale Run Cleanup

If a Run's process died (crash, kill), `GetActiveRun` detects it via `kill(pid, 0)` and marks it as `error`.

## Inspecting Runs

```bash
# List runs in a topic (with summaries)
topic runs <topic-id> [limit]

# Show a run's full messages
topic run <run-id>

# Check async run status + output
get-run <run-id>
```
