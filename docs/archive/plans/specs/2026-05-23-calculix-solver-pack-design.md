# CalculiX Solver Pack 最小方案 — 设计文档

> **Goal:** 用户零依赖完成 CalculiX 可用——从官方 dhondt.de 一键下载/解压/校验/写入配置

## 1. 概述

当前 CalculiX 安装需用户自行下载、解压、手动粘贴路径。Solver Pack 通过 SSE 进度流的后台安装流程，将"下载→解压→扫描→校验→写配置"自动化。

**验收标准：**
- 工具链页 CalculiX 卡片显示"安装 Solver Pack"按钮
- 点击后显示实时进度（下载/解压/验证百分比）
- 完成后卡片状态从 missing → verified，路径自动写入 `.simfea/config.json`
- 安装失败（下载断开/校验失败）有明确错误提示

## 2. 数据模型变更

### SolverInstallSpec 新增字段

```python
# src/backends/simfea_api/config.py
@dataclass
class SolverInstallSpec:
    # ... existing fields ...
    download_url: str = ""           # 官方 zip 下载地址
    managed_install_root: str = ""   # 管理安装根目录，如 %LOCALAPPDATA%\SimFEA\solvers
```

### 默认配置（calculix）

```python
"download_url": "http://www.dhondt.de/ccx_2.21_win64.zip",
"managed_install_root": "%LOCALAPPDATA%\\SimFEA\\solvers",
```

## 3. 后端 API

### 3.1 触发安装

```
POST /v1/toolchain/solvers/calculix/install
Response 202: { "install_id": "uuid", "message": "安装已启动" }
Error 409:   已有一个安装进行中
```

### 3.2 SSE 进度流

```
GET /v1/toolchain/solvers/calculix/install/{install_id}/events
Content-Type: text/event-stream
```

事件类型：

```jsonl
{"type":"install_progress","step":"download","progress_pct":18,"message":"正在下载 CalculiX..."}
{"type":"install_progress","step":"extract","progress_pct":55,"message":"正在解压..."}
{"type":"install_progress","step":"verify","progress_pct":90,"message":"正在验证..."}
{"type":"install_complete","data":{ ... SolverInstallation ... }}
{"type":"install_error","message":"下载失败: Connection reset"}
```

### 3.3 安装流程

```
1. 检查是否已有进行中的安装 → 有则返回 409
2. 创建 install_id，后台 async 执行:
   a. 下载 (0%→40%): httpx 流式下载到 .simfea/_tmp/calculix_{id}.zip
   b. 解压 (40%→80%): zipfile 解压到 %LOCALAPPDATA%\SimFEA\solvers\calculix\
   c. 扫描 (80%→90%): 递归子目录找 ccx.bat/ccx.exe
   d. 校验 (90%→100%): 调用已有 _verify_solver_install("calculix")
   e. 写入 config.json
3. 推送 install_complete 或 install_error
```

### 3.4 实现文件

| 文件 | 职责 |
|------|------|
| `src/backends/simfea_api/config.py` | SolverInstallSpec 新增 download_url/managed_install_root |
| `src/backends/main.py` | 2 个路由 + 后台安装函数 |
| `src/backends/simfea_api/schemas.py` | install_progress/install_complete/install_error 事件模型 |
| `app/api/contracts.ts` | installCalculixContract + 事件 schema |
| `app/api/simfeaClient.ts` | installCalculix() + getInstallEvents() 方法 |
| `app/components/ToolchainManager.vue` | 安装按钮 + 进度条 UI |

## 4. 前端 UI

### 4.1 按钮状态

```
未安装（missing）:
  [安装 Solver Pack] 按钮（绿色 primary-action）

安装中:
  按钮区域替换为:
  ████████░░░░░░ 45%  正在下载 CalculiX...
  按钮隐藏

已完成（verified）:
  正常卡片状态，无安装按钮
  "已通过测试运行" 状态标签

失败（install_error）:
  错误信息 + [重试] 按钮
```

### 4.2 前端数据流

```
点击安装 → POST /install → 获取 install_id
         → 打开 SSE events/{install_id}
         → 每条 install_progress 更新进度条
         → install_complete → 调用 loadInstallations() 刷新
         → install_error → 显示错误 + 重试选项
```

### 4.3 技术细节

- SSE 连接复用现有 `useRunEvents` 的 EventSource 模式（但 ToolchainManager 直接用 fetch + ReadableStream 更简单）
- 进度条用 CSS `width: X%` + transition
- 按钮 disabled 状态阻止重复点击
- 安装中关闭页面时 SSE 自动断开（后台安装继续不中断）

## 5. 错误处理

| 场景 | 处理 |
|------|------|
| 下载 URL 不可达 | install_error，message 包含 HTTP 状态 |
| 磁盘空间不足 | install_error，message 提示清理 |
| 解压后找不到 ccx | install_error，列出解压内容 |
| 校验失败 | install_error，附 stdout/stderr |
| 已有安装进行中 | 409 Conflict |
| 不是 calculix alias | 400 Bad Request |

## 6. 测试

- **后端单元测试**: `test_solver_install.py`
  - mock httpx 下载 → 验证进度事件序列
  - mock zip 解压 → 验证文件扫描逻辑
  - 验证 409 冲突检测
- **前端**: 无需新增测试（UI 变更在已有组件内）

## 7. 不做什么

- 不自动检测已有 CalculiX 安装（已有"自动搜索"按钮做这个）
- 不支持多 solver Pack（只做 calculix）
- 不做下载断点续传
- 不做 SHA256 校验（下载完整性靠 zip 内建 CRC）
- 不做跨平台（Windows only，URL 硬编码 Windows 包）
