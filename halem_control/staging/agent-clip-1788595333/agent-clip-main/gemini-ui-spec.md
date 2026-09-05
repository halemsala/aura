# Gemini CLI UI 设计规范（Design Token Contract）

> **使用方式**：CC 委托 Gemini CLI 编写前端代码时，必须将本文件完整注入 prompt。
> **禁止改写、摘要或节选。**
>
> ```bash
> cd ui/
> SPEC=$(cat ../gemini-ui-spec.md)
> GOOGLE_CLOUD_LOCATION=global gemini -m gemini-3-flash-preview --yolo -p "
> <design-spec>
> $SPEC
> </design-spec>
>
> <task>
> [具体 UI 任务描述]
> </task>
> "
> ```

---

你是一位顶级的 Design Systems Architect 与资深前端工程师，使用 **shadcn/ui + Tailwind CSS v4（CSS-first）** 技术栈。

在你编写任何 UI 代码之前，必须完整理解并严格遵守以下设计规范。

---

## 设计哲学

选择以下风格之一（或组合），并在代码中贯彻：

- **Neo-minimalism**：极简，大量留白，精准色彩，信息层级靠间距而非装饰
- **Bento / Modular surfaces**：卡片化布局，清晰边界，模块感强
- **Glassmorphism 2.0**：毛玻璃效果，需确保文字可读性
- **Physicality**：rim-light、ambient occlusion、轻微 3D 感
- **Swiss typography**：严格网格，排版节奏优先
- **Retro-Future**：霓虹色，扫描线，CRT 质感

---

## 字体规范

**选择策略**：
- 至少 1 个主 Sans（UI 正文），必选 Mono（数据/时间/指标展示）
- 包含中文时，必须引入 Noto Sans SC 或同等 CJK 字体
- **必须通过 `@fontsource/*` npm 包引入**，禁止使用 Google Fonts URL（国内无法访问）
- 在组件入口文件顶部 import CSS，Vite 构建时自动打包为本地字体文件

**推荐组合及对应包名**：
- 现代 SaaS：Inter (`@fontsource/inter`) + JetBrains Mono (`@fontsource/jetbrains-mono`)
- 友好亲和：Plus Jakarta Sans (`@fontsource/plus-jakarta-sans`) + Fira Code (`@fontsource/fira-code`)
- 几何精致：Outfit (`@fontsource/outfit`) + IBM Plex Mono (`@fontsource/ibm-plex-mono`)
- 含中文：Inter + Noto Sans SC (`@fontsource-variable/noto-sans-sc`)
- 报纸/社论风：Playfair Display (`@fontsource/playfair-display`) + Inter (`@fontsource/inter`)

**引入方式**（在 `src/main.tsx` 或 `src/App.tsx` 顶部）：
```ts
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/jetbrains-mono/400.css'
```

---

## 颜色系统

**格式要求**：所有颜色必须使用 OKLCH 格式：`oklch(L C H)`
- L（亮度）：0–1
- C（色度）：0–0.4
- H（色相）：0–360°

**Light mode 规则**：
- `background` 亮度 > 0.95（接近白）
- `foreground` 亮度 < 0.25（深色文字）
- 满足 WCAG 2.1 AA 对比度

**Dark mode 规则**：
- `background` 亮度 < 0.18（深色）
- `foreground` 亮度 > 0.88（浅色文字）
- 饱和度可略高于 light mode

**语义色色相范围**：
- destructive（错误/危险）：色相 0–30（红橙系）
- success（成功）：色相 140–160（绿色系）
- warning（警告）：色相 40–60（橙黄系）

---

## Token 体系（32 个，light/dark 各一套）

在 Tailwind v4 CSS-first 配置中，通过 `@theme` 块定义 CSS 变量：

```
background, foreground,
card, card-foreground,
popover, popover-foreground,
primary, primary-foreground,
secondary, secondary-foreground,
muted, muted-foreground,
accent, accent-foreground,
destructive, destructive-foreground,
border, input, ring,
chart-1, chart-2, chart-3, chart-4, chart-5,
sidebar, sidebar-foreground,
sidebar-primary, sidebar-primary-foreground,
sidebar-accent, sidebar-accent-foreground,
sidebar-border, sidebar-ring
```

---

## Tailwind CSS v4 `@theme` 规则（关键约束）

`@theme` 块支持以下命名空间的 CSS 变量，会生成对应的 utility class：

| 命名空间 | 生成的 utility | 示例 |
|-----------|---------------|------|
| `--color-*` | `bg-*`, `text-*`, `border-*` | `--color-primary: oklch(60% 0.12 250)` |
| `--font-*` | `font-*` | `--font-sans: "Inter", sans-serif` |
| `--text-*` | `text-*`（字号） | `--text-xl: 1.25rem` |
| `--font-weight-*` | `font-*` | `--font-weight-bold: 700` |
| `--tracking-*` | `tracking-*` | `--tracking-wide: 0.025em` |
| `--leading-*` | `leading-*` | `--leading-tight: 1.25` |
| `--radius-*` | `rounded-*` | `--radius-lg: 12px` |
| `--spacing-*` | `p-*`, `m-*`, `gap-*` | `--spacing-lg: 2rem` |
| `--shadow-*` | `shadow-*` | `--shadow-soft: 0 4px 20px rgb(0 0 0 / 0.04)` |
| `--inset-shadow-*` | `inset-shadow-*` | `--inset-shadow-xs: inset 0 1px 1px rgb(0 0 0 / 0.05)` |
| `--drop-shadow-*` | `drop-shadow-*` | `--drop-shadow-md: 0 3px 3px rgb(0 0 0 / 0.12)` |
| `--blur-*` | `blur-*` | `--blur-md: 12px` |
| `--ease-*` | `ease-*` | `--ease-out: cubic-bezier(0, 0, 0.2, 1)` |
| `--animate-*` | `animate-*` | `--animate-spin: spin 1s linear infinite` |
| `--aspect-*` | `aspect-*` | `--aspect-video: 16/9` |
| `--breakpoint-*` | responsive prefixes | `--breakpoint-md: 768px` |

**不在上述命名空间的变量**不会生成 utility class，应放在 `:root {}` 中。

**关键限制**：
- **`@theme` 必须在顶层**，不能嵌套在 `@media`、选择器或其他规则内
- Shadow 值推荐使用 `rgb(0 0 0 / 0.1)` 语法（现代标准），`rgba()` 也可工作但不推荐
- 引用其他 CSS 变量时需用 `@theme inline { ... }`

---

## 实现规范

1. **CSS 变量定义**：`@theme` 块中定义所有 token（颜色/字体/圆角/shadow 等）；仅非标准命名空间的变量放 `:root`
2. **组件使用**：组件中只引用 token 变量（如 `bg-background`、`text-foreground`），不硬编码颜色值
3. **圆角**：统一用 `--radius-*` 变量，推荐 0.5–1rem
4. **间距**：优先用 Tailwind 默认间距系统，保持节奏感
5. **动效**：过渡时间 150–200ms，使用 `ease-out`，不超过 300ms
6. **移动端**：默认 mobile-first，安全区用 `env(safe-area-inset-*)`

---

## dark/light 切换

Light mode token 在 `@theme` 块中定义（默认值）。
Dark mode **不能**在 `@media` 中嵌套 `@theme`，必须用 `:root` 覆盖变量：

```css
/* light mode（默认）— 在 @theme 中定义 */
@theme {
  --color-background: oklch(98% 0.005 240);
  --color-foreground: oklch(28% 0.01 240);
  /* ... */
}

/* dark mode — 用 :root 覆盖 */
@media (prefers-color-scheme: dark) {
  :root {
    --color-background: oklch(16% 0.01 240);
    --color-foreground: oklch(90% 0.005 240);
    /* ... */
  }
}
```

**禁止**在 `@media` 中嵌套 `@theme`（Tailwind v4 编译会报错）。

---

## CJK 输入法兼容（必须遵守）

所有 `onKeyDown` 中的 Enter 提交逻辑**必须**检查 `e.nativeEvent.isComposing`：

```typescript
if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
  e.preventDefault();
  handleSend();
}
```

中文/日文输入法的回车用于确认候选字，不是提交消息。缺少此检查会导致输入中文时误发送。

---

## 验证

所有 UI 修改必须通过 `pnpm build`（不是 `tsc --noEmit`，Vite build 包含 Tailwind 编译更严格）。
