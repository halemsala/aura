# Agent Clip

AI Agent 作为 [Pinix Clip](https://github.com/epiral/pinix) — 带记忆、工具调用、视觉和异步执行的 agentic loop。

[English](README.md) | [中文](README.zh-CN.md)

## 快速开始

```bash
# 本地开发
make dev                              # 编译 macOS binary + 从 seed/ 初始化 data/
cd ui && pnpm install && cd ..        # 安装前端依赖（首次）

# 在 data/config.yaml 中添加 API key

# 对话
bin/agent-local send -p "hello"

# 构建前端
make ui                               # ui/ → web/
```

## 安装

### 作为 Pinix Clip 安装

```bash
# 打包
make package                          # → dist/agent.clip

# 安装到 Pinix Server
pinix clip install dist/agent.clip --server http://localhost:9875 --token <super-token>

# 升级（保留 data/）
pinix clip upgrade dist/agent.clip
```

## 功能

- **Agentic Loop**：LLM → 工具调用 → 执行 → 迭代 → 响应
- **多协议 LLM**：支持 OpenAI、Anthropic 及兼容 API
- **工具系统**：单一 `run(command, stdin?)` 函数，Unix 风格子命令
- **Clip-to-Clip**：连接其他 Clip（如 sandbox 执行代码）
- **浏览器控制**：集成 [bb-browser](https://github.com/yan5xu/bb-browser) 实现网页自动化
- **记忆**：语义搜索对话历史（SQLite + vec0 向量）
- **事件**：定时事件 + cron 调度
- **初始化向导**：首次运行引导配置，7 个 provider 预设
- **Web UI**：流式聊天界面，文件上传，中英文双语

## 架构

```
Agent Clip
  │
  ├─ commands/          外部接口（Pinix ClipService.Invoke）
  │   send, create-topic, list-topics, get-run, cancel-run, config
  │
  ├─ run(cmd, stdin?)   LLM 唯一的 function call
  │   ├─ 文件：  ls, cat, write, stat, rm, cp, mv, mkdir
  │   ├─ 记忆：  memory search/recent/store/facts/forget
  │   ├─ 话题：  topic list/info/runs/run/search/rename
  │   ├─ Clip：  clip <name> <command> [args...] / pull / push
  │   ├─ 浏览器：browser <action> [params...]（自动保存截图）
  │   ├─ 链式：  cmd1 | cmd2 && cmd3 ; cmd4 || cmd5
  │   └─ 工具：  echo, time, help, grep, head, tail, wc
  │
  ├─ Topics             命名对话空间（SQLite）
  ├─ Runs               每次 send 一个 agentic loop（同步/异步）
  ├─ Memory             摘要 + 向量嵌入 + 事实 + 语义搜索
  ├─ Vision             浏览器截图自动附加为视觉内容
  └─ Output             CLI (raw) / Web (jsonl) 双输出
```

## 配置

首次打开 Agent 时，Setup 向导引导你完成配置：

1. 选择 AI 服务商（OpenRouter / OpenAI / Anthropic / DashScope / MiniMax / DeepSeek / 自定义）
2. 输入 API Key
3. 选择模型
4. 开始对话

配置存储在 `data/config.yaml`，通过 `commands/config` 管理：

```bash
# 查看配置（JSON，key 脱敏）
commands/config

# 设置值（支持 dot-path）
commands/config set llm_model anthropic/claude-sonnet-4-6
commands/config set providers.deepseek.api_key sk-xxx

# 管理 Clip 连接
commands/config add-clip '{"name":"sandbox","url":"...","token":"..."}'
commands/config remove-clip sandbox
```

## 三层模型

| 层 | 内容 | 可变性 |
|----|------|--------|
| **Workspace**（本 repo） | 源代码、构建工具 | 开发时 |
| **Package**（`.clip` ZIP） | clip.yaml + commands/ + bin/ + seed/ + web/ | 不可变 |
| **Instance**（Pinix Server 上） | Package 解包 + data/（从 seed/ 初始化） | 仅 data/ 可变 |

`seed/` 在 install 时初始化 `data/`；`clip upgrade` 替换一切但保留 `data/`。

## 构建

| 命令 | 说明 |
|------|------|
| `make build-local` | macOS 本地 binary |
| `make build` | Linux arm64（BoxLite 沙箱用） |
| `make ui` | 构建前端 ui/ → web/ |
| `make dev` | build-local + 初始化 data/ |
| `make deploy` | build + ui（workdir 模式） |
| `make package` | 打包 → dist/agent.clip |
| `make clean` | 清理 bin/ data/ web/ dist/ |
