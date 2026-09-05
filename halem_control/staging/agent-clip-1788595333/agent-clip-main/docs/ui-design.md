这是一份基于 **Neo-minimalism + Swiss typography** 风格的完整 UI/UX 设计体系文档，专为 Clip Dock (桌面 Electron + iOS 移动端) 打造。设计严格遵守给定的设计 token 规范与底层 Agent API 数据结构。

---

## 1. 页面清单（Information Architecture）

应用采用典型的单页应用（SPA）架构，分为以下几个核心视图：

*   **主控台视图 (Main Chat Interface)**
    *   **职责**：核心交互区，负责对话呈现、思考过程展示、Tool Call 状态追踪以及消息输入。
    *   **入口**：应用默认首页。
    *   **导航关系**：通过左侧栏（或移动端抽屉）切换不同的 Topic。
*   **话题历史视图 (Topic Sidebar)**
    *   **职责**：展示历史 Topic 列表（`listTopics`），支持新建对话（`createTopic`）。
    *   **入口**：桌面端常驻左侧，移动端通过主视图顶部的汉堡菜单（Hamburger Menu）呼出。
*   **全局配置视图 (Agent Config Modal)**
    *   **职责**：修改 Agent 配置（如 LLM Provider、API Key、System Prompt、Clips 注册等）。调用 `getConfig` 和 `setConfig`。
    *   **入口**：话题历史视图底部的“设置”图标。
    *   **导航关系**：以全局 Dialog/Sheet 形式覆盖在当前页面上。

---

## 2. 响应式策略（Responsive Strategy）

基于 `mobile-first` 原则，布局在屏幕宽度达到 `md` (768px) 时发生形态转换：

*   **移动端 (iOS/屏幕 < 768px)**
    *   **布局**：单列（Single-pane）。主控台占满全屏。
    *   **导航**：Sidebar 转换为左侧滑出的抽屉（Drawer / Sheet）。
    *   **安全区适配**：顶部 Header 需附加 `pt-[env(safe-area-inset-top)]`，底部输入区需附加 `pb-[env(safe-area-inset-bottom)]`。
    *   **交互**：支持屏幕左侧边缘右滑呼出 Topic 列表。
*   **桌面端 (Electron/屏幕 >= 768px)**
    *   **布局**：双栏（Two-pane）。左侧 Sidebar（宽度固定约 260px，可折叠），右侧主控台弹性填满剩余空间。
    *   **导航**：Sidebar 常驻，直接点击列表项切换 (`selectTopic`)。
    *   **拖拽区**：顶部预留 `-webkit-app-region: drag` 的无干扰区域供 Electron 窗口拖拽。

---

## 3. 每个页面的线框描述（Wireframe）

### 3.1 桌面端布局 (Desktop)
```text
[ 窗口控制区 (无UI，仅拖拽) ]
+-------------------------+---------------------------------------------------+
| [新建对话按钮 (Primary)]| [顶部 Header] 当前 Topic 名称                     |
|                         |                                                   |
| [搜索历史 (Input)]      | [消息列表区 (ScrollArea)]                         |
|                         |  - User Msg (靠右/底色强调)                       |
| [Topic 列表 (按时间)]   |  - Assistant Msg (靠左)                           |
|  - 话题 A (Active)      |    > [Thinking] (折叠面板)                        |
|  - 话题 B               |    > [Tool Call: clip sandbox bash ls] (执行中)   |
|  - 话题 C               |    > 文本内容流式输出...                          |
|                         |                                                   |
| [底栏]                  | [输入区]                                          |
| [配置图标] [用户/状态]  |  [ Textarea (Auto-resize) ]  [ 发送/取消按钮 ]    |
+-------------------------+---------------------------------------------------+
```

### 3.2 移动端布局 (iOS)
```text
+---------------------------------------------------+
| [ 状态栏安全区 env(safe-area-inset-top) ]         |
| [≡ 菜单图标]  当前 Topic 名称            [新建图标] |
+---------------------------------------------------+
| [消息列表区]                                      |
|  - User Msg                                       |
|  - Assistant Msg                                  |
|    > [Thinking]                                   |
|    > [Tool Call]                                  |
|    > Text...                                      |
|                                                   |
|                                                   |
+---------------------------------------------------+
| [输入区]                                          |
|  [ Textarea ] [ 发送/取消 ]                       |
| [ 底部安全区 env(safe-area-inset-bottom) ]        |
+---------------------------------------------------+

* 侧边栏通过点击 [≡] 从左侧作为 Sheet 滑出覆盖在上面。
```

---

## 4. 组件清单（Component Inventory）

遵循 shadcn/ui 命名标准，主要包括基础组件与业务组件：

**基础组件 (Base UI)**
*   `Button`: 按钮（支持 icon, default, ghost, destructive 等变体）。
*   `Input` / `Textarea`: 文本输入（Textarea 需支持随内容高度自适应）。
*   `ScrollArea`: 滚动容器，隐藏原生滚动条，提供精致的滚动视觉。
*   `Sheet`: 用于移动端 Sidebar 和配置页面的滑出面板。
*   `Dialog`: 用于桌面端展示配置页面。
*   `Collapsible`: 用于折叠 Thinking 过程和 Tool Call 结果。

**业务组件 (Domain UI)**
*   `ChatLayout`: 响应式外壳，处理 Sidebar 与 Main 视图的协同。
*   `TopicList`: 渲染 `Topic[]`，高亮 `currentTopicId`，显示 `message_count` 与时间。
*   `MessageList`: 遍历渲染 `ChatMessage[]`。
*   `MessageBubble`: 区分 `user` 和 `assistant`。采用极简设计，不加气泡背景框，而是用缩进和头像/Icon区分层级。
*   `ThinkingBlock`: 展示 `msg.thinking`，标题栏带旋转的 Loader，结束时显示 "Thought process"。
*   `ToolCallBlock`: 渲染 `ToolCallEntry`。
    *   执行中：黄色/蓝色呼吸点，展示 `name` 和 `arguments` (Monospace 字体)。
    *   完成：展示执行时间，折叠态展示 `result`。
*   `ChatComposer`: 绑定 `useChat().send` 和 `cancel`。根据 `isStreaming` 切换发送与停止按钮图标。

---

## 5. 交互规范（Interaction Patterns）

### 5.1 流式消息与自动滚动 UX
*   当 `isStreaming` 为 true 且收到新 token (`onText` / `onThinking`) 时，如果用户滚动条在底部（容差 50px），则**自动滚动到底部**。
*   如果用户主动向上滑动（打断阅读），停止自动滚动，并在底部显示“悬浮向下箭头 (↓)”，点击后强制回滚到底部并恢复自动滚动追踪。

### 5.2 Thinking 与 Tool Call 展示
*   **流式执行中**：`ThinkingBlock` 和 `ToolCallBlock` 处于展开状态，实时显示 token 涌入。
*   **执行结束 (`status === 'done'`)**：自动将 `ThinkingBlock` 折叠（默认收起以节约空间），保留核心输出文本。`ToolCallBlock` 变为紧凑的一行，指示调用成功，用户需要时可点击展开看 raw `result`。
*   **字体**：工具名（如 `clip sandbox read`）与参数强制使用 `JetBrains Mono` 字体，呈现极客/CLI质感。

### 5.3 错误处理 (Error Handling)
*   **全局级**（如 `useChat` 抛出的 `error`）：在顶部弹出轻量级的 Toast (Destructive 色系)。
*   **消息级**（如 `msg.status === "error"`）：在对应的 Assistant 消息底部显示红色的错误文本块，并提供 "Retry" 小按钮。

### 5.4 空状态 (Empty State)
*   未选择 Topic 且无历史记录时：屏幕中央显示应用 Logo 与 "How can I help you today?"，下方提供几个预设的快捷指令（如 "Check system config", "List sandbox files"）点击即发。

### 5.5 移动端手势与键盘
*   **键盘弹起**：iOS 下 Textarea 聚焦时，通过 `visualViewport` API 或 `dvh` 单位保证输入框贴合键盘顶部。
*   **发送行为**：移动端换行使用 `Return` 键，发送使用右侧独立的 Send 按钮；桌面端回车直接发送，`Shift+Enter` 换行。

---

## 6. 设计风格（Design Tokens）

基于 **Neo-minimalism (新极简主义) + Swiss typography (瑞士排版)**。
界面放弃多余的卡片投影，通过精确的留白（Spacing）、排版律动和极简线条来区分层级。高度依赖 OKLCH 色彩体系带来的纯净度。

### 6.1 字体映射
在 `src/main.tsx` 中引入：
```tsx
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource-variable/noto-sans-sc'
import '@fontsource/jetbrains-mono/400.css'
```

### 6.2 完整的 `index.css` (Tailwind v4)

严格遵照规范，提供基于 OKLCH 的全局系统与自动暗色切换：

```css
@import "tailwindcss";

/* 注入字体集 */
@theme {
  --font-sans: "Inter", "Noto Sans SC Variable", "Noto Sans SC", sans-serif;
  --font-mono: "JetBrains Mono", monospace;
  
  /* 圆角规范 - 极简主义选用微圆角 */
  --radius: 0.5rem;
  
  /* ---------------- Light Mode Tokens (默认) ---------------- */
  --color-background: oklch(0.99 0 0); /* 极亮白 */
  --color-foreground: oklch(0.18 0 0); /* 深灰偏黑，确保对比度 */
  
  --color-card: oklch(0.98 0 0);
  --color-card-foreground: oklch(0.18 0 0);
  
  --color-popover: oklch(1 0 0);
  --color-popover-foreground: oklch(0.18 0 0);
  
  --color-primary: oklch(0.2 0 0); /* 接近黑色的主色 */
  --color-primary-foreground: oklch(0.98 0 0);
  
  --color-secondary: oklch(0.95 0 0);
  --color-secondary-foreground: oklch(0.25 0 0);
  
  --color-muted: oklch(0.96 0 0); /* 浅灰背景，用于 Thinking 块 */
  --color-muted-foreground: oklch(0.5 0 0); /* 次要文字 */
  
  --color-accent: oklch(0.94 0 0);
  --color-accent-foreground: oklch(0.2 0 0);
  
  --color-destructive: oklch(0.6 0.2 25); /* 柔和红 */
  --color-destructive-foreground: oklch(0.98 0 0);
  
  --color-success: oklch(0.65 0.15 150); /* 柔和绿，用于 Tool Call 成功 */
  
  --color-border: oklch(0.92 0 0); /* 极细描边 */
  --color-input: oklch(0.92 0 0);
  --color-ring: oklch(0.8 0 0);

  --color-sidebar: oklch(0.97 0 0);
  --color-sidebar-foreground: oklch(0.25 0 0);
  --color-sidebar-primary: oklch(0.2 0 0);
  --color-sidebar-primary-foreground: oklch(0.98 0 0);
  --color-sidebar-accent: oklch(0.93 0 0);
  --color-sidebar-accent-foreground: oklch(0.2 0 0);
  --color-sidebar-border: oklch(0.92 0 0);
  --color-sidebar-ring: oklch(0.8 0 0);
}

/* ---------------- Dark Mode Tokens ---------------- */
@media (prefers-color-scheme: dark) {
  @theme {
    --color-background: oklch(0.14 0 0); /* 深空灰 */
    --color-foreground: oklch(0.95 0 0); /* 浅灰白 */
    
    --color-card: oklch(0.16 0 0);
    --color-card-foreground: oklch(0.95 0 0);
    
    --color-popover: oklch(0.15 0 0);
    --color-popover-foreground: oklch(0.95 0 0);
    
    --color-primary: oklch(0.95 0 0); /* 白色主按钮 */
    --color-primary-foreground: oklch(0.15 0 0);
    
    --color-secondary: oklch(0.2 0 0);
    --color-secondary-foreground: oklch(0.9 0 0);
    
    --color-muted: oklch(0.18 0 0);
    --color-muted-foreground: oklch(0.65 0 0);
    
    --color-accent: oklch(0.22 0 0);
    --color-accent-foreground: oklch(0.95 0 0);
    
    --color-destructive: oklch(0.45 0.18 25); /* 深色模式下的红 */
    --color-destructive-foreground: oklch(0.95 0 0);
    
    --color-success: oklch(0.5 0.15 150);
    
    --color-border: oklch(0.22 0 0);
    --color-input: oklch(0.22 0 0);
    --color-ring: oklch(0.35 0 0);

    --color-sidebar: oklch(0.12 0 0);
    --color-sidebar-foreground: oklch(0.8 0 0);
    --color-sidebar-primary: oklch(0.95 0 0);
    --color-sidebar-primary-foreground: oklch(0.15 0 0);
    --color-sidebar-accent: oklch(0.18 0 0);
    --color-sidebar-accent-foreground: oklch(0.95 0 0);
    --color-sidebar-border: oklch(0.18 0 0);
    --color-sidebar-ring: oklch(0.35 0 0);
  }
}

/* 基础样式重置与全局设定 */
@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground font-sans antialiased selection:bg-primary/20;
    /* 桌面端阻止全页面反弹，将滚动控制在特定区域内 */
    overscroll-behavior-y: none;
  }
  
  /* 滚动条极简化定制 (WebKit) */
  ::-webkit-scrollbar {
    width: 4px;
    height: 4px;
  }
  ::-webkit-scrollbar-track {
    background: transparent;
  }
  ::-webkit-scrollbar-thumb {
    @apply bg-muted-foreground/30 rounded-full;
  }
  ::-webkit-scrollbar-thumb:hover {
    @apply bg-muted-foreground/50;
  }
}
```
