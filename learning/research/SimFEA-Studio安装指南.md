# SimFEA Studio 安装指南

本指南提供 Windows 平台下 SimFEA Studio 从零到运行的完整安装说明。

**技术栈**：Tauri 2 (Rust) + Vue 3 (TypeScript) + FastAPI (Python) + VTK.js

预计完成时间：**30-60 分钟**（取决于网络和已有环境）

---

## 系统要求

- Windows 10/11 64 位
- 至少 4GB 可用磁盘空间
- 稳定的网络连接（用于下载依赖）

---

## 1. 安装 Node.js

SimFEA Studio 前端使用 Vite + Vue 3，包管理器为 pnpm。

### 步骤

1. 访问 [Node.js 官网](https://nodejs.org/)
2. 下载 **LTS 版本**（推荐 20.x 或 22.x）
3. 运行安装程序，全部默认即可

### 验证

```powershell
node --version   # 应显示 v20.x.x 或 v22.x.x
npm --version    # 应显示 10.x.x 或更高
```

### 启用 pnpm

Node.js 自带的 `corepack` 可以直接启用 pnpm：

```powershell
corepack enable pnpm
pnpm --version   # 应显示 9.x.x
```

> **注意**：如果 `pnpm` 命令不可用，重启终端后再试。corepack 需要首次激活后重新加载 PATH。

---

## 2. 安装 Python

SimFEA Studio 的 sidecar 后端使用 FastAPI，Python 3.9 以上即可，推荐 3.11。

### 步骤

1. 访问 [Python 官网](https://www.python.org/downloads/)
2. 下载 **Windows installer (64-bit)**，推荐 Python 3.11.x
3. 运行安装程序，**务必勾选**：
   - ✅ **Add Python to PATH**
4. 点击 Install Now

### 验证

```powershell
python --version   # 应显示 Python 3.11.x
pip --version      # 应显示 pip 24.x 或更高
```

### （可选）使用 Miniconda

如果你需要管理多个 Python 版本，推荐使用 Miniconda：

```powershell
# 创建专用环境
conda create -n simfea python=3.11
conda activate simfea
```

---

## 3. 安装 Rust

Tauri 桌面壳用 Rust 编写，需要安装 Rust 工具链。

### 步骤

1. 访问 [rustup.rs](https://rustup.rs/)
2. 下载并运行 `rustup-init.exe`
3. 选择默认安装（选项 1）

### 验证

```powershell
rustc --version   # 应显示 rustc 1.x.x
cargo --version   # 应显示 cargo 1.x.x
```

---

## 4. 安装 Tauri 系统依赖（Windows）

Tauri 2 在 Windows 上需要两个额外的系统组件。

### 4.1 Microsoft Visual Studio C++ Build Tools

1. 访问 [Visual Studio 下载页](https://visualstudio.microsoft.com/downloads/)
2. 下载 **Build Tools for Visual Studio 2022**
3. 运行安装程序，勾选 **"Desktop development with C++"**
4. 确认以下组件被选中：
   - MSVC v143 编译器
   - Windows 11 SDK (10.0.22621.0 或更高)
   - C++ CMake tools for Windows

> 安装大小约 8GB，完成后需重启终端。

### 4.2 WebView2

Windows 10/11 通常已预装 WebView2。如果没有：

1. 访问 [WebView2 下载页](https://developer.microsoft.com/microsoft-edge/webview2/)
2. 下载 **Evergreen Bootstrapper**
3. 运行安装

### 验证 Tauri 环境

```powershell
cargo install tauri-cli --version "^2.0"
cargo tauri --version
```

> 如果 `cargo install tauri-cli` 编译时间过长（10-20 分钟），这是正常的——它在编译 Rust 依赖。只需等待。

---

## 5. 克隆并安装项目

### 5.1 克隆仓库

```powershell
git clone https://github.com/yd5768365-hue/simFEA-studio.git
cd simFEA-studio
```

### 5.2 安装前端依赖

```powershell
pnpm install
```

首次运行会下载 ~500MB 的 node_modules，需要 1-3 分钟。

### 5.3 安装 Python 依赖

```powershell
pip install -e .
```

这会安装 FastAPI、uvicorn、httpx 等后端依赖。

### 验证安装

```powershell
# 验证前端可构建
npx vue-tsc --noEmit

# 验证 Python 可导入
python -c "from simfea_api.config import load_config; print('OK')"
```

---

## 6. 配置求解器

SimFEA Studio 需要一个配置文件来声明求解器路径。

### 6.1 创建配置目录

```powershell
New-Item -ItemType Directory -Force .simfea
```

### 6.2 创建最小配置文件

在 `.simfea/config.json` 中写入：

```json
{
  "compute": {
    "default_node": "local",
    "nodes": [
      {
        "alias": "local",
        "label": "本机",
        "host": "localhost"
      }
    ]
  },
  "solvers": []
}
```

如果你已经安装了 CalculiX，可以加上求解器配置（具体路径按实际情况修改）：

```json
{
  "solvers": [
    {
      "alias": "calculix",
      "executable": "C:\\CalculiX\\bin\\ccx.bat",
      "command_template": "C:\\CalculiX\\bin\\ccx.bat cantilever"
    }
  ]
}
```

> CalculiX 在 Windows 上必须使用 `ccx.bat`（不是 `ccx.exe`），因为 `.bat` 会自动设置 `OMP_NUM_THREADS` 和 DLL 路径。

---

## 7. 启动项目

### 7.1 仅启动前后端（调试用，无桌面窗口）

```powershell
# 终端 1：启动 Python sidecar
python src/backends/main.py
# 输出：Uvicorn running on http://0.0.0.0:8008

# 终端 2：启动 Vite 前端
pnpm dev:frontend
# 输出：VITE v6.x.x ready — Local: http://localhost:1420/
```

然后浏览器访问 `http://localhost:1420/`。

### 7.2 启动桌面版（完整 Tauri 应用）

```powershell
pnpm dev:tauri
```

这条命令会自动：
1. 启动 Vite 前端开发服务器
2. 编译 Rust Tauri 壳（首次编译需 5-15 分钟）
3. 启动 Python sidecar
4. 打开原生桌面窗口

> **首次编译 Tauri 需要较长时间**，这是正常的。后续修改前端代码会通过 HMR 秒级热更新；修改 Rust 代码才需要重新编译。

---

## 8. 验证一切正常

### 8.1 运行测试

```powershell
# Python 单元测试（87 个）
python -m unittest discover -s src/backends/tests -v

# 前端 Vitest 测试（23 个）
pnpm test
```

### 8.2 端到端验证

桌面版启动后，确认以下事项：

- [ ] 侧边导航栏显示 9 个标签页
- [ ] 左下角连接状态显示绿色圆点（已连接 sidecar）
- [ ] 切换到"作业"标签页，可以切换本地/远程模式
- [ ] 切换到"工具"标签页，可以看到求解器列表
- [ ] 切换到"基准"标签页，可以看到基准案例列表

---

## 常见问题

### pnpm 报错 "Cannot find module"

```powershell
# 原因：pnpm 安装损坏
# 解决：
npm install -g pnpm
```

### Tauri 编译报错 "找不到 MSVC"

```
# 原因：未安装 Visual Studio Build Tools
# 解决：按第 4.1 节安装
```

### Python sidecar 启动报错 "ModuleNotFoundError: simfea_api"

```powershell
# 原因：Python 包未安装
# 解决：
pip install -e .
```

### 端口 8008 或 1420 被占用

```powershell
# 查看占用端口的进程
netstat -ano | findstr :8008
netstat -ano | findstr :1420

# 修改 Vite 端口：编辑 vite.config.js 中的 server.port
# 修改 sidecar 端口：在 main.py 中搜索 8008 并替换
```

### Windows 上 `asyncio.create_subprocess_shell` 卡住

这是已知问题。SimFEA Studio 已经在代码层面通过 `subprocess.run` + `loop.run_in_executor` 处理了，不需要额外操作。

### HMR 更新后某些标签页数据显示过期

这是由于 `<KeepAlive>` 缓存组件导致的。切换到其他标签页再切回来即可触发数据刷新（所有数据加载组件都已使用 `onActivated`）。

---

## 开发命令速查

| 命令 | 作用 |
|------|------|
| `pnpm install` | 安装前端依赖 |
| `pip install -e .` | 安装 Python 依赖 |
| `pnpm dev:tauri` | 启动桌面版（含 sidecar + 前端） |
| `pnpm dev:frontend` | 仅启动 Vite 前端 |
| `python src/backends/main.py` | 仅启动 sidecar |
| `pnpm test` | 运行前端测试 |
| `python -m unittest discover -s src/backends/tests -v` | 运行后端测试 |
| `pnpm lint` | 前端代码检查 |
| `pnpm format` | 前端代码格式化 |
| `pnpm build` | 前端生产构建 |

---

## 技术栈版本参考

| 组件 | 版本 | 用途 |
|------|------|------|
| Node.js | 20.x / 22.x | JavaScript 运行时 |
| pnpm | 9.x | 前端包管理器 |
| Python | 3.11+ | 后端语言 |
| Rust | 1.60+ | 桌面壳 |
| Tauri | 2.x | 桌面框架 |
| Vue | 3.5 | 前端框架 |
| Vite | 6.x | 前端构建工具 |
| FastAPI | 0.95 | Python Web 框架 |
| VTK.js | 34.x | 3D 结果可视化 |
| CalculiX | 2.10+ | 有限元求解器 |
