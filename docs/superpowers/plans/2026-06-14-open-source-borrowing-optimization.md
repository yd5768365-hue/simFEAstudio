# Open Source Borrowing Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn selected open-source CAE project patterns into small, verifiable SimFEA Studio improvements without expanding the project beyond its workbench boundary.

**Architecture:** This first iteration adds a borrowing matrix and a read-only Benchmark Lab contract checker. The checker validates that each benchmark case has the minimal evidence structure needed for comparison and learning, without changing case data.

**Tech Stack:** Markdown docs, Python stdlib, existing `unittest` test style.

---

### Task 1: Borrowing Matrix

**Files:**
- Create: `docs/OPEN_SOURCE_BORROWING_MATRIX.md`

- [ ] **Step 1: Write the borrowing matrix**

Create a Chinese markdown document with these sections:

```markdown
# Open Source Borrowing Matrix

## 借鉴原则

- 只借工作台能力，不借大平台体量。
- 优先借案例结构、求解器适配、证据归档、教程分层和工作流表达。
- 不把 SimFEA Studio 变成求解器、CAD 内核或工业级协同平台。

## 项目矩阵

| 项目 | 值得借鉴 | 不借什么 | 第一轮落地 |
| --- | --- | --- | --- |
```

Add rows for FreeCAD, SALOME, Gmsh, OpenFOAM, FEniCSx/DOLFINx, and MFEM.

- [ ] **Step 2: Verify the document references real project boundaries**

Run: `Select-String -Path docs\OPEN_SOURCE_BORROWING_MATRIX.md -Pattern "不把 SimFEA Studio 变成求解器"`

Expected: one matching line.

### Task 2: Benchmark Contract Checker

**Files:**
- Create: `scripts/check_benchmark_contract.py`
- Create: `src/backends/tests/test_benchmark_contract.py`

- [ ] **Step 1: Write the failing tests**

Create tests that import `check_case` from `scripts/check_benchmark_contract.py` and verify:

```python
def test_valid_case_passes(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "case.json").write_text('{"title":"Rod","methods":["analytic"],"level":"L1"}', encoding="utf-8")
    (case_dir / "问题描述.md").write_text("# Rod\n", encoding="utf-8")
    (case_dir / "results").mkdir()
    (case_dir / "results" / "对比结果.csv").write_text("method,value\nanalytic,1\n", encoding="utf-8")
    assert check_case(case_dir) == []

def test_missing_problem_description_is_reported(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "case.json").write_text('{"title":"Rod","methods":["analytic"],"level":"L1"}', encoding="utf-8")
    issues = check_case(case_dir)
    assert "missing problem markdown" in issues
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest src.backends.tests.test_benchmark_contract -v`

Expected: FAIL or ERROR because `scripts.check_benchmark_contract` does not exist.

- [ ] **Step 3: Write minimal checker**

Implement `check_case(case_dir: Path) -> list[str]` with these rules:

```python
REQUIRED_CASE_KEYS = ("title", "methods", "level")

def check_case(case_dir: Path) -> list[str]:
    issues = []
    case_json = case_dir / "case.json"
    if not case_json.exists():
        return ["missing case.json"]
    data = json.loads(case_json.read_text(encoding="utf-8"))
    for key in REQUIRED_CASE_KEYS:
        if key not in data:
            issues.append(f"missing case.json key: {key}")
    if not any(case_dir.glob("*问题描述.md")) and not (case_dir / "problem.md").exists():
        issues.append("missing problem markdown")
    results_dir = case_dir / "results"
    if not results_dir.exists():
        issues.append("missing results directory")
    elif not any(results_dir.glob("*.csv")):
        issues.append("missing results csv")
    return issues
```

Add a CLI that scans `learning/benchmarks` and exits non-zero when any issue exists.

- [ ] **Step 4: Run focused tests**

Run: `python -m unittest src.backends.tests.test_benchmark_contract -v`

Expected: PASS.

- [ ] **Step 5: Run checker on current benchmarks**

Run: `python scripts/check_benchmark_contract.py`

Expected: PASS if all 13 current cases satisfy the minimal contract, or a clear list of existing gaps if not.

### Task 3: Project Verification Hook

**Files:**
- Modify: `README.md`
- Modify: `package.json`

- [ ] **Step 1: Add documentation pointer**

Add one short README bullet pointing to `docs/OPEN_SOURCE_BORROWING_MATRIX.md` and the benchmark checker.

- [ ] **Step 2: Add package script**

Add:

```json
"check:benchmarks": "python scripts/check_benchmark_contract.py"
```

- [ ] **Step 3: Run verification**

Run:

```powershell
python -m unittest src.backends.tests.test_benchmark_contract -v
python scripts/check_benchmark_contract.py
pnpm test
```

Expected: new test passes, benchmark checker reports current status, frontend tests are not broken by docs/script changes.
