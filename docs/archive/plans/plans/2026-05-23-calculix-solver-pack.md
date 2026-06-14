# CalculiX Solver Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One-click CalculiX install from official dhondt.de — download, extract, scan, verify, write config — with SSE progress streaming.

**Architecture:** New `install.py` module holds the background install task + SSE event generator (uses `asyncio.Queue` for in-memory state passing, same pattern as run events). Two new routes in `main.py` (POST trigger + GET SSE stream). Frontend uses native `EventSource` to consume progress events and update button state.

**Tech Stack:** Python (FastAPI, httpx, zipfile, asyncio), TypeScript (Vue 3, EventSource, Zod contracts)

---

### Task 1: Config data model — add download_url and managed_install_root

**Files:**
- Modify: `src/backends/simfea_api/config.py:92-102` (SolverInstallSpec)
- Modify: `src/backends/simfea_api/config.py:365-379` (calculix solver_install_specs entry)
- Modify: `src/backends/simfea_api/config.py:460-473` (load_settings solver_install_specs loop)

- [ ] **Step 1: Add fields to SolverInstallSpec dataclass**

```python
# src/backends/simfea_api/config.py, replace lines 92-102
@dataclass
class SolverInstallSpec:
    alias: str
    label: str
    install_mode: str
    executable_candidates: list[str]
    common_paths: list[str]
    verify_command: str
    install_hint: str = ""
    install_guide_url: str = ""
    input_extensions: list[str] = field(default_factory=list)
    download_url: str = ""
    managed_install_root: str = ""
```

- [ ] **Step 2: Add download_url and managed_install_root to calculix spec**

```python
# src/backends/simfea_api/config.py, in default_config() > solver_install_specs, replace the calculix entry (lines 365-379)
{
    "alias": "calculix",
    "label": "CalculiX",
    "install_mode": "managed_or_external",
    "executable_candidates": ["ccx.bat", "ccx.exe", "ccx"],
    "common_paths": [
        "%LOCALAPPDATA%\\SimFEA\\solvers\\calculix\\bin\\ccx.exe",
        "%PROGRAMFILES%\\CalculiX\\bin\\ccx.exe",
        "%SIMFEA_SOLVERS_ROOT%\\calculix\\bin\\ccx.exe",
    ],
    "verify_command": "\"${executable}\"",
    "install_hint": "可以使用已有 CalculiX，也可以点击「安装 Solver Pack」一键下载安装。",
    "install_guide_url": "https://www.dhondt.de/",
    "input_extensions": [".inp"],
    "download_url": "http://www.dhondt.de/ccx_2.21_win64.zip",
    "managed_install_root": "%LOCALAPPDATA%\\SimFEA\\solvers",
},
```

- [ ] **Step 3: Read new fields in load_settings**

```python
# src/backends/simfea_api/config.py, inside load_settings() solver_install_specs loop, replace lines 460-473
solver_install_specs = {}
for item in raw_config.get("solver_install_specs", []):
    spec = SolverInstallSpec(
        alias=item["alias"],
        label=item.get("label") or item["alias"],
        install_mode=item.get("install_mode", "external"),
        executable_candidates=list(item.get("executable_candidates", [])),
        common_paths=list(item.get("common_paths", [])),
        verify_command=item.get("verify_command", ""),
        install_hint=item.get("install_hint", ""),
        install_guide_url=item.get("install_guide_url", ""),
        input_extensions=list(item.get("input_extensions", [])),
        download_url=item.get("download_url", ""),
        managed_install_root=item.get("managed_install_root", ""),
    )
    solver_install_specs[spec.alias] = spec
```

- [ ] **Step 4: Run existing tests to verify no regression**

```powershell
python -m unittest discover -s src/backends/tests -v
```

Expected: all 75 tests pass (or same count as before).

- [ ] **Step 5: Commit**

```bash
git add src/backends/simfea_api/config.py
git commit -m "feat: add download_url and managed_install_root to SolverInstallSpec"
```

---

### Task 2: Backend install module — download/extract/scan/verify + SSE routes

**Files:**
- Create: `src/backends/simfea_api/install.py`
- Modify: `src/backends/main.py` (add 2 routes + import)
- Create: `src/backends/tests/test_solver_install.py`

- [ ] **Step 1: Create install.py with core functions**

```python
# src/backends/simfea_api/install.py
import asyncio
import os
import shutil
import uuid
import zipfile
from pathlib import Path

import httpx

from .config import settings
from .logger import create_logger

log = create_logger("install")

_installs: dict[str, dict] = {}


def _expand_path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value)))


async def start_install(alias: str) -> dict:
    current = settings()
    spec = current.solver_install_specs.get(alias)
    if spec is None:
        raise ValueError(f"Solver install spec not found: {alias}")
    if not spec.download_url:
        raise ValueError(f"Solver {alias} does not support managed install.")

    for install_id, state in _installs.items():
        if state.get("alias") == alias and state.get("status") == "running":
            raise RuntimeError("安装已在运行中")

    install_id = f"install_{uuid.uuid4().hex[:10]}"
    queue: asyncio.Queue = asyncio.Queue()
    _installs[install_id] = {
        "alias": alias,
        "status": "running",
        "queue": queue,
    }
    asyncio.create_task(_run_install(install_id, alias, spec))
    return {"install_id": install_id, "message": "安装已启动"}


async def _run_install(install_id: str, alias: str, spec):
    state = _installs.get(install_id)
    if state is None:
        return
    queue = state["queue"]

    async def emit(event_type: str, **payload):
        await queue.put({"type": event_type, **payload})

    # Download (0% → 40%)
    await emit("install_progress", step="download", progress_pct=0, message="正在下载 CalculiX...")
    tmp_dir = settings().config_path.parent / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    zip_path = tmp_dir / f"calculix_{install_id}.zip"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0), follow_redirects=True) as client:
            async with client.stream("GET", spec.download_url) as response:
                if response.status_code != 200:
                    await emit("install_error", message=f"下载失败: HTTP {response.status_code}")
                    state["status"] = "error"
                    return
                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                with open(zip_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = int(downloaded / total * 40)
                            await emit("install_progress", step="download", progress_pct=pct, message=f"正在下载 CalculiX... {downloaded // 1024}/{total // 1024} KB")
    except Exception as exc:
        await emit("install_error", message=f"下载失败: {exc}")
        state["status"] = "error"
        return

    # Extract (40% → 80%)
    await emit("install_progress", step="extract", progress_pct=40, message="正在解压...")
    install_root = _expand_path(spec.managed_install_root)
    extract_dir = install_root / "calculix"
    try:
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            total_files = len(names)
            for i, name in enumerate(names):
                zf.extract(name, extract_dir)
                if total_files > 0:
                    pct = 40 + int(i / total_files * 40)
                    await emit("install_progress", step="extract", progress_pct=pct, message=f"正在解压... {i + 1}/{total_files}")
    except Exception as exc:
        await emit("install_error", message=f"解压失败: {exc}")
        state["status"] = "error"
        return
    finally:
        if zip_path.exists():
            zip_path.unlink()

    # Scan (80% → 90%)
    await emit("install_progress", step="scan", progress_pct=80, message="正在扫描可执行文件...")
    found_exe = ""
    for root, dirs, files in os.walk(extract_dir):
        for f in files:
            if f.lower() in ("ccx.bat", "ccx.exe"):
                found_exe = str(Path(root) / f)
                break
        if found_exe:
            break

    if not found_exe:
        extracted = []
        for root, dirs, files in os.walk(extract_dir):
            for f in files:
                extracted.append(str(Path(root) / f))
                if len(extracted) >= 20:
                    break
            if len(extracted) >= 20:
                break
        await emit("install_error", message=f"解压后未找到 ccx.bat 或 ccx.exe。解压内容: {extracted}")
        state["status"] = "error"
        return

    await emit("install_progress", step="scan", progress_pct=90, message=f"找到可执行文件: {found_exe}")

    # Verify (90% → 100%) — reuse _verify_solver_install from main
    await emit("install_progress", step="verify", progress_pct=90, message="正在验证...")
    try:
        from main import _verify_solver_install, _update_solver_executable
        result = await _verify_solver_install(alias, found_exe)
        if not result.get("verified"):
            await emit("install_error", message=f"校验失败: {result.get('stderr', '未知错误')}")
            state["status"] = "error"
            return

        _update_solver_executable(alias, found_exe)
        await emit("install_progress", step="verify", progress_pct=100, message="安装完成")
        await emit("install_complete", data=result)
        state["status"] = "done"
    except Exception as exc:
        await emit("install_error", message=f"校验失败: {exc}")
        state["status"] = "error"


async def event_generator(install_id: str):
    state = _installs.get(install_id)
    if state is None:
        import json
        yield {
            "event": "message",
            "data": json.dumps({"type": "install_error", "message": "安装任务未找到"}, ensure_ascii=False),
        }
        return

    queue = state["queue"]
    import json
    while True:
        event = await queue.get()
        yield {
            "event": "message",
            "data": json.dumps(event, ensure_ascii=False),
        }
        if event["type"] in ("install_complete", "install_error"):
            break
```

- [ ] **Step 2: Add routes to main.py**

Add import at the top of main.py (after the existing simfea_api imports):

```python
# src/backends/main.py — add to the try/except import block (after the simfea_api.config import line)
try:
    from .simfea_api.install import start_install, event_generator
except ImportError:
    from simfea_api.install import start_install, event_generator
```

Add two routes before the `def kill_process():` line (before line 1914):

```python
@app.post("/v1/toolchain/solvers/{alias}/install")
async def install_solver_pack(alias: str):
    if alias != "calculix":
        raise HTTPException(status_code=400, detail="Solver pack 目前仅支持 calculix。")
    try:
        result = await start_install(alias)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/v1/toolchain/solvers/{alias}/install/{install_id}/events")
async def stream_install_events(alias: str, install_id: str):
    return EventSourceResponse(event_generator(install_id))
```

- [ ] **Step 3: Run existing tests to verify imports work**

```powershell
python -m unittest discover -s src/backends/tests -v
```

Expected: all existing tests pass (new module doesn't break anything).

- [ ] **Step 4: Write backend unit tests**

```python
# src/backends/tests/test_solver_install.py
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from simfea_api.install import start_install, _installs


class TestSolverInstall(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _installs.clear()

    async def test_start_install_rejects_non_calculix(self):
        with self.assertRaises(ValueError):
            await start_install("freecad")

    async def test_start_install_rejects_missing_download_url(self):
        with patch("simfea_api.install.settings") as mock_settings:
            mock_spec = MagicMock()
            mock_spec.download_url = ""
            mock_settings.return_value.solver_install_specs = {"calculix": mock_spec}
            with self.assertRaises(ValueError):
                await start_install("calculix")

    async def test_start_install_returns_install_id(self):
        with patch("simfea_api.install.settings") as mock_settings:
            mock_spec = MagicMock()
            mock_spec.download_url = "http://example.com/ccx.zip"
            mock_spec.managed_install_root = "%LOCALAPPDATA%\\SimFEA\\solvers"
            mock_settings.return_value.solver_install_specs = {"calculix": mock_spec}
            mock_settings.return_value.config_path.parent = MagicMock()
            mock_settings.return_value.config_path.parent.__truediv__ = MagicMock(return_value=MagicMock())

            result = await start_install("calculix")
            self.assertIn("install_id", result)
            self.assertIn("message", result)

    async def test_start_install_rejects_concurrent(self):
        with patch("simfea_api.install.settings") as mock_settings:
            mock_spec = MagicMock()
            mock_spec.download_url = "http://example.com/ccx.zip"
            mock_spec.managed_install_root = "%LOCALAPPDATA%\\SimFEA\\solvers"
            mock_settings.return_value.solver_install_specs = {"calculix": mock_spec}
            mock_settings.return_value.config_path.parent = MagicMock()
            mock_settings.return_value.config_path.parent.__truediv__ = MagicMock(return_value=MagicMock())

            await start_install("calculix")
            with self.assertRaises(RuntimeError):
                await start_install("calculix")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 5: Run tests**

```powershell
python -m unittest src/backends/tests/test_solver_install.py -v
```

Expected: 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/backends/simfea_api/install.py src/backends/main.py src/backends/tests/test_solver_install.py
git commit -m "feat: add CalculiX Solver Pack backend — download/extract/scan/verify with SSE"
```

---

### Task 3: Frontend API contracts — install endpoint + events

**Files:**
- Modify: `app/api/contracts.ts` (add install schemas)
- Modify: `app/api/simfeaClient.ts` (add installSolver method + expose baseUrl)

- [ ] **Step 1: Add install schemas to contracts.ts**

Add after the `solverInstallationResponseSchema` at the end of contracts.ts (after line 466):

```typescript
// ── Solver Pack Install ───────────────────────────────────────

export const installSolverResponseSchema = z.object({
  install_id: z.string(),
  message: z.string(),
})

export type InstallSolverResponse = z.output<typeof installSolverResponseSchema>

export const installProgressEventSchema = z.object({
  type: z.literal('install_progress'),
  step: z.enum(['download', 'extract', 'scan', 'verify']),
  progress_pct: z.number(),
  message: z.string(),
})

export const installCompleteEventSchema = z.object({
  type: z.literal('install_complete'),
  data: solverInstallationSchema,
})

export const installErrorEventSchema = z.object({
  type: z.literal('install_error'),
  message: z.string(),
})

export const installEventSchema = z.discriminatedUnion('type', [
  installProgressEventSchema,
  installCompleteEventSchema,
  installErrorEventSchema,
])

export type InstallProgressEvent = z.output<typeof installProgressEventSchema>
export type InstallCompleteEvent = z.output<typeof installCompleteEventSchema>
export type InstallErrorEvent = z.output<typeof installErrorEventSchema>
export type InstallEvent = z.output<typeof installEventSchema>
```

- [ ] **Step 2: Add install contract and expose baseUrl in simfeaClient.ts**

Add import for the new schema at the top (add to the existing import from contracts):

```typescript
// app/api/simfeaClient.ts — add installSolverResponseSchema to the existing import block
import {
  // ... existing imports ...
  installSolverResponseSchema,
} from '@/api/contracts'
```

Add contract definition (before the `createSimfeaClient` function, after the guidedQuestionsContract):

```typescript
const installSolverContract = contract({
  method: 'POST',
  path: '/v1/toolchain/solvers/:alias/install',
  params: ['alias'] as const,
  response: installSolverResponseSchema,
})
```

Add `baseUrl` to the returned client object and `installSolver` method:

```typescript
// app/api/simfeaClient.ts — inside createSimfeaClient, add to the return object:
export function createSimfeaClient(baseUrl: string, appendLog: (line: string) => void) {
  const { request } = createClient(baseUrl, appendLog)

  return {
    baseUrl,
    // ... all existing methods remain ...
    installSolver: (alias: string) => request(installSolverContract, { params: { alias } }),
  }
}
```

- [ ] **Step 3: Run frontend typecheck**

```powershell
pnpm exec vue-tsc --noEmit
```

Expected: no new type errors.

- [ ] **Step 4: Commit**

```bash
git add app/api/contracts.ts app/api/simfeaClient.ts
git commit -m "feat: add installSolver contract + baseUrl exposure for SSE construction"
```

---

### Task 4: ToolchainManager install button + progress bar UI

**Files:**
- Modify: `app/components/ToolchainManager.vue`

- [ ] **Step 1: Add install state and functions to script section**

Add after the `const message = ref('')` line (after line 26):

```typescript
const installProgress = reactive<Record<string, { pct: number; message: string; step: string }>>({})
const installError = reactive<Record<string, string>>({})
```

Add `installSolver` function after `pickFile` function (after line 140):

```typescript
async function installSolver(alias: string) {
  installError[alias] = ''
  installProgress[alias] = { pct: 0, message: '正在启动安装...', step: 'download' }
  try {
    const result = await props.api.installSolver(alias)
    const url = `${props.api.baseUrl}/v1/toolchain/solvers/${alias}/install/${result.install_id}/events`
    const es = new EventSource(url)
    es.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'install_progress') {
        installProgress[alias] = { pct: data.progress_pct, message: data.message, step: data.step }
      } else if (data.type === 'install_complete') {
        es.close()
        delete installProgress[alias]
        setInstallation(data.data)
        message.value = `${data.data.label} 安装完成，已通过测试运行。`
      } else if (data.type === 'install_error') {
        es.close()
        delete installProgress[alias]
        installError[alias] = data.message
      }
    }
    es.onerror = () => {
      es.close()
      delete installProgress[alias]
      installError[alias] = 'SSE 连接中断，安装可能仍在后台进行。请刷新状态查看结果。'
    }
  } catch {
    delete installProgress[alias]
    installError[alias] = '无法启动安装，请检查后端连接。'
  }
}
```

- [ ] **Step 2: Add install button and progress UI to template**

In the template, in the calculix card (the `v-for="item in installations"` block), add the install button area. After the `install-empty-state` div (after line 222), add:

```html
<div v-if="installProgress[item.alias]" class="install-progress-bar">
  <div class="install-progress-fill" :style="{ width: installProgress[item.alias].pct + '%' }"></div>
  <span class="install-progress-text">{{ installProgress[item.alias].message }}</span>
</div>

<div v-if="installError[item.alias]" class="install-error-message">
  <p>{{ installError[item.alias] }}</p>
  <button type="button" @click="installSolver(item.alias)">重试</button>
</div>
```

Add the install button inside `tool-install-actions` div, before the existing buttons. Only show for `managed_or_external` items with `status === 'missing'`:

```html
<button
  v-if="item.install_mode === 'managed_or_external' && item.status === 'missing' && !installProgress[item.alias]"
  type="button"
  class="primary-action"
  @click="installSolver(item.alias)"
  :disabled="Boolean(busy[item.alias])"
>
  安装 Solver Pack
</button>
```

- [ ] **Step 3: Add minimal CSS for progress bar**

Add to the existing `<style>` block (or inline styles if no scoped style block exists — check the file):

```css
.install-progress-bar {
  position: relative;
  height: 28px;
  background: var(--color-bg-muted, #e5e7eb);
  border-radius: 4px;
  overflow: hidden;
  margin-top: 8px;
}

.install-progress-fill {
  height: 100%;
  background: var(--color-primary, #2563eb);
  transition: width 0.3s ease;
}

.install-progress-text {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.8rem;
  color: #fff;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

.install-error-message {
  margin-top: 8px;
  padding: 8px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 4px;
  font-size: 0.85rem;
  color: #991b1b;
}

.install-error-message button {
  margin-top: 4px;
}
```

- [ ] **Step 4: Run linting**

```powershell
pnpm lint
```

Expected: no lint errors.

- [ ] **Step 5: Commit**

```bash
git add app/components/ToolchainManager.vue
git commit -m "feat: add Solver Pack install button with SSE progress bar"
```
