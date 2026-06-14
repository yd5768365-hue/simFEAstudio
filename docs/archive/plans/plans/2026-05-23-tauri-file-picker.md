# Tauri 文件选择器接入工具链页

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 工具链管理页的"选择路径"按钮通过 Tauri 原生文件对话框选取可执行文件，替代手动粘贴路径。

**Architecture:** 添加 `tauri-plugin-dialog`（Rust + JS），在 ToolchainManager.vue 中调用 `open()` 打开系统文件选择器，选择后自动填入路径并写入配置文件。

**Tech Stack:** Tauri v2, Vue 3 + TypeScript, `@tauri-apps/plugin-dialog`

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `src-tauri/Cargo.toml` | 添加 Rust dialog 插件依赖 |
| 修改 | `src-tauri/src/main.rs` | 注册 dialog 插件 |
| 修改 | `src-tauri/capabilities/migrated.json` | 授予 dialog 权限 |
| 修改 | `package.json` | 添加 JS dialog 包 |
| 修改 | `app/components/ToolchainManager.vue` | 接入原生文件对话框 |

---

### Task 1: 添加 Rust 侧 tauri-plugin-dialog 依赖和注册

**Files:**
- Modify: `src-tauri/Cargo.toml:23`
- Modify: `src-tauri/src/main.rs:113`
- Modify: `src-tauri/capabilities/migrated.json:7`

- [ ] **Step 1: 在 Cargo.toml 添加依赖**

在 `src-tauri/Cargo.toml` 的 `[dependencies]` 中添加一行：

```toml
tauri-plugin-dialog = "2"
```

插入位置：`tauri-plugin-http = "2"` 之后。

- [ ] **Step 2: 在 main.rs 注册插件**

在 `src-tauri/src/main.rs` 的 `main()` 函数中，`.plugin(tauri_plugin_shell::init())` 之后添加：

```rust
.plugin(tauri_plugin_dialog::init())
```

- [ ] **Step 3: 在 capabilities 中添加 dialog 权限**

在 `src-tauri/capabilities/migrated.json` 的 `permissions` 数组中，`"core:window:default"` 之后添加：

```json
"dialog:default",
```

- [ ] **Step 4: Commit**

```bash
git add src-tauri/Cargo.toml src-tauri/src/main.rs src-tauri/capabilities/migrated.json
git commit -m "chore: add tauri-plugin-dialog dependency and permissions"
```

---

### Task 2: 安装 JS 侧 @tauri-apps/plugin-dialog

**Files:**
- Modify: `package.json`

- [ ] **Step 1: 安装 npm 包**

```bash
pnpm add @tauri-apps/plugin-dialog
```

- [ ] **Step 2: Commit**

```bash
git add package.json pnpm-lock.yaml
git commit -m "chore: add @tauri-apps/plugin-dialog JS package"
```

---

### Task 3: ToolchainManager 接入文件选择器

**Files:**
- Modify: `app/components/ToolchainManager.vue`

- [ ] **Step 1: 添加 import**

在 `<script setup>` 顶部，`import type { SimfeaClient }` 之后添加：

```ts
import { open } from '@tauri-apps/plugin-dialog'
```

- [ ] **Step 2: 添加 pickFile 函数和 Tauri 可用性检测**

在 `busy` 变量声明之后添加：

```ts
const isTauri = typeof window !== 'undefined' && '__TAURI__' in window
```

在 `verify` 函数之后添加：

```ts
async function pickFile(alias: string) {
  if (!isTauri) {
    message.value = '文件选择器仅在桌面应用中可用，请手动粘贴路径。'
    return
  }
  try {
    const selected = await open({
      multiple: false,
      directory: false,
      filters: [{
        name: '可执行文件',
        extensions: ['exe', 'bat', 'com', 'cmd'],
      }],
    })
    if (selected && typeof selected === 'string') {
      pathInputs[alias] = selected
      await savePath(alias)
    }
  } catch {
    message.value = '无法打开文件选择器，请检查应用权限或使用手动输入。'
  }
}
```

- [ ] **Step 3: 修改"选择路径"按钮绑定**

将第 188 行的按钮：
```html
<button type="button" @click="savePath(item.alias)" :disabled="Boolean(busy[item.alias])">
  选择路径
</button>
```

改为：
```html
<button type="button" @click="pickFile(item.alias)" :disabled="Boolean(busy[item.alias])">
  选择路径
</button>
```

- [ ] **Step 4: 验证 TypeScript 编译**

```bash
pnpm exec vue-tsc --noEmit --project tsconfig.json 2>&1 | head -20
```

预期：无新增类型错误。

- [ ] **Step 5: Commit**

```bash
git add app/components/ToolchainManager.vue
git commit -m "feat: integrate Tauri native file picker for solver executable selection"
```

---

### Task 4: 端到端验证

- [ ] **Step 1: Rust 编译验证**

```bash
cd src-tauri && cargo check 2>&1 | tail -5
```

预期：`Checking simfea-studio` 无 error。

- [ ] **Step 2: 前端构建验证**

```bash
pnpm build 2>&1 | tail -10
```

预期：构建成功，无报错。

- [ ] **Step 3: 功能验证清单（需在 Tauri 桌面应用中手动测试）**

1. 打开工具链管理页
2. 点击任一求解器的"选择路径"按钮
3. 确认系统原生文件对话框弹出
4. 选择一个可执行文件（如 `ccx.bat`）
5. 确认路径自动填入输入框
6. 确认路径已写入 `.simfea/config.json`
7. 确认 message 提示"路径已写入配置"
8. 点击"测试运行"验证求解器可用
