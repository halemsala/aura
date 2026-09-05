# External Clips

## Concept

External Clips are independent services that the agent invokes via the Pinix protocol. The agent treats all external capabilities uniformly — whether they're remote Pinix Clips or local sidecars, the invocation is the same.

```
Agent Clip
  │
  │  run("clip sandbox bash ls")
  │  → parsed: clip=sandbox, command=bash, args=[ls]
  │  → pinix invoke bash --server <url> --token <token> -- ls
  │
  ▼
Pinix Server → Sandbox Clip (BoxLite VM)
  └── commands/bash → sh -c "ls"
```

## Configuration

Clips are configured in `data/config.yaml`:

```yaml
clips:
  - name: sandbox
    url: http://localhost:9875      # Pinix Server URL
    token: <clip-token>             # ClipService token
    commands: [bash, read, write, edit]  # cached from GetInfo
```

Fields:
- `name`: identifier used in `clip <name> <command>`
- `url`: Pinix Server URL where the Clip is registered
- `token`: Clip Token for authentication
- `commands`: available commands (for tool description generation)

## Invocation

The `clip` command is a built-in `run` command:

```
clip list                           List connected clips
clip <name>                         Show clip details
clip <name> <command> [args...]     Invoke clip command
```

### Args Passthrough

Arguments after the command name are passed directly to `pinix invoke`:

```
run("clip sandbox bash ls -la /tmp")
→ pinix invoke bash --server <url> --token <token> -- ls -la /tmp
```

The sandbox's `bash` command joins all args and passes to `sh -c`.

### Stdin

When the LLM provides `stdin`, it's piped to the clip command:

```
run("clip sandbox write /tmp/file.txt", stdin="hello world")
→ echo "hello world" | pinix invoke write --server ... -- /tmp/file.txt
```

### Pipes

Clip output can be piped to text processing commands:

```
run("clip sandbox bash find / -name '*.go' | grep main | head 5")
```

This is an agent-level pipe: `clip sandbox bash find ...` runs in the sandbox, its full output is piped to the agent's `grep`, then `head`.

## Implementation

`InvokeClip` in `internal/clip.go` shells out to the `pinix` CLI:

```go
cmd := exec.Command("pinix", "invoke", command,
    "--server", clip.URL,
    "--token", clip.Token,
    "--", args...)
```

BoxLite VM logs on stderr are filtered out; only stdout is returned.

## clip-sandbox

The reference external Clip: [epiral/clip-sandbox](https://github.com/epiral/clip-sandbox)

Provides sandboxed execution in a BoxLite micro-VM (Linux arm64):

| Command | Usage | Description |
|---------|-------|-------------|
| `bash` | `clip sandbox bash <command>` | Execute shell command |
| `read` | `clip sandbox read <path>` | Read file contents |
| `write` | `clip sandbox write <path>` (stdin = content) | Write file |
| `edit` | `clip sandbox edit <path> "old" "new"` | Find and replace |

## Adding a New Clip

1. Create and deploy the Clip on a Pinix Server
2. Generate a Clip Token: `pinix token generate --clip <clip-id>`
3. Add to `data/config.yaml`:
   ```yaml
   clips:
     - name: my-clip
       url: http://server:9875
       token: <token>
       commands: [cmd1, cmd2]
   ```
4. The agent can now use: `run("clip my-clip cmd1 arg1 arg2")`
