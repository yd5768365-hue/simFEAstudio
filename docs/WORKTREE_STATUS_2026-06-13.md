# Worktree Status 2026-06-13

## 目的

这份清单用于冻结当前工作区事实，避免在大量未提交变更上继续叠功能时丢失边界。它只记录分类，不删除、不回滚、不替用户决定提交范围。

## 当前观察

`git status --short` 显示工作区包含多类变更：

- 前端 API、契约、样式、工具函数和 composable 变更。
- 后端配置、结果解析、FRD/VTK、schema、推理接口和测试变更。
- 文档从 `docs/` 根目录迁移到 `docs/dev-logs/` 与 `docs/archive/`。
- 图片资源从仓库根目录迁移到 `extras/`。
- Benchmark Lab、solver-dev、work 资料库和 preflight 相关模块作为未跟踪资产存在。
- `package-lock.json` 与 `pnpm-lock.yaml` 同时存在，需要后续确认包管理器边界。
- 根目录出现未跟踪文件 `-w`，需要确认来源后再决定是否删除。
- `cantilever.inp` 已删除，需要确认是否已迁移到案例目录或不再需要。

## 建议分组

### 1. 文档与资源迁移

候选文件：

- `docs/dev-logs/`
- `docs/archive/`
- `extras/`
- `docs/DEVLOG_LOCATION.md`
- `AGENTS.md`

处理建议：单独提交。这个分组主要是项目文档位置、历史归档和资源整理，不应和功能代码混在一起。

### 2. Benchmark Lab 案例资产

候选文件：

- `learning/benchmarks/`
- `scripts/import-benchmarks.py`
- `scripts/build-benchmark-html.js`
- `app/composables/useBenchmark.ts`
- `app/components/BenchmarkLab.vue`
- `app/components/MethodLabView.vue`
- `app/composables/useMethodLab.ts`

处理建议：作为“案例库 + Method Lab 数据化”提交。提交前验证 `/v1/benchmarks` 返回 13 个案例，前端 Benchmark Lab / Method Lab 不白屏。

### 3. pip / FastAPI 独立启动

候选文件：

- `package.json`
- `pyproject.toml`
- `MANIFEST.in`
- `scripts/build_pip.py`
- `src/backends/main.py`
- `src/backends/demo_runs/`

处理建议：作为“分发路径”提交。提交前在干净环境验证 `pip install -e .` 和 `simfea-studio`。

### 4. 后端结果与证据链

候选文件：

- `src/backends/simfea_api/results.py`
- `src/backends/simfea_api/frd_to_vtk.py`
- `src/backends/simfea_api/frd_dat_reader.py`
- `src/backends/tests/test_results.py`
- `src/backends/tests/test_frd_to_vtk.py`

处理建议：作为“结果解析与 VTK 证据”提交。提交前运行相关后端测试。

### 5. CAE preflight / solver-dev 资产

候选文件：

- `src/backends/cae_preflight_lib/`
- `src/backends/routers/preflight.py`
- `learning/solver-dev/`

处理建议：单独审查。这个分组可能体量较大，不建议夹在 Benchmark 或 pip 分发提交里。

### 6. 可疑残留

候选项：

- `-w`
- `test_llm_output.txt`
- `package-lock.json`
- `learning/work/`

处理建议：先确认来源，再决定是否保留或删除。不要在未确认前清理。

## 下一步最小验证

```powershell
python -m json.tool learning\benchmarks\01_一维杆拉伸\case.json
python -m unittest src.backends.tests.test_results src.backends.tests.test_frd_to_vtk -v
pnpm test
```

如果只处理案例索引，至少验证所有 `case.json` 可解析、README 案例数与目录数一致。
