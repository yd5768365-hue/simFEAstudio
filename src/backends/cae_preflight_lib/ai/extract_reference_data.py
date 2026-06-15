# extract_reference_data.py
"""
从 CalculiX 官方测试集批量提取参考数据。

用法：
    python -m cae.ai.extract_reference_data <test_dir> <output_json>

示例：
    python -m cae.ai.extract_reference_data \
        "D:/CAE-CLI/cae-cli/ccx_2.23.test/CalculiX/ccx_2.23/test" \
        "cae/ai/data/reference_cases.json"
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cae_preflight_lib.ai.reference_cases import (
    parse_inp_metadata,
)


def parse_dat_ref(ref_path: Path) -> dict:
    """
    从 .dat.ref 文件解析位移和应力结果。

    .dat.ref 使用定宽格式：
    - 位移行: "    node_id    vx    vy    vz"
    - 应力行: "    elem  intp    sxx    syy    szz    sxy    sxz    syz"

    返回：
        {
            "disp_max": float,
            "disp_min": float,
            "stress_max": float,
            "stress_min": float,
        }
    """
    if not ref_path.exists():
        return {}

    text = ref_path.read_text(encoding="latin-1", errors="replace")
    NUMBER_PATTERN = r'[+-]?\d+\.\d+E[+-]\d+'

    disp_values = []
    stress_values = []

    lines = text.splitlines()
    i = 0
    in_disp_block = False
    in_stress_block = False

    while i < len(lines):
        line = lines[i]
        ul = line.upper()

        # 检测块开始
        if "DISPLACEMENTS" in ul and "FOR SET" in ul:
            in_disp_block = True
            in_stress_block = False
            i += 1
            continue

        if "STRESSES" in ul and "FOR SET" in ul:
            in_stress_block = True
            in_disp_block = False
            i += 1
            continue

        # 处理位移块内容
        if in_disp_block:
            if not line.strip():
                i += 1
                continue
            if line.strip().startswith("-"):
                # 分隔线
                i += 1
                continue
            if "STRESSES" in ul or "DISPLACEMENT" in ul or "=" in ul:
                # 遇到下一个块
                in_disp_block = False
                i += 1
                continue

            nums = re.findall(NUMBER_PATTERN, line)
            if len(nums) >= 3:
                # 位移值是 vx, vy, vz，取每个节点的最大分量
                try:
                    disp_magnitude = max(abs(float(n)) for n in nums[:3])
                    disp_values.append(disp_magnitude)
                except ValueError:
                    pass
            i += 1
            continue

        # 处理应力块内容
        if in_stress_block:
            if not line.strip():
                i += 1
                continue
            if line.strip().startswith("-"):
                # 分隔线
                i += 1
                continue
            if "DISPLACEMENT" in ul or "STRESS" in ul and "FOR" not in ul:
                in_stress_block = False
                i += 1
                continue

            nums = re.findall(NUMBER_PATTERN, line)
            if len(nums) >= 6:
                for n in nums[:6]:
                    try:
                        stress_values.append(abs(float(n)))
                    except ValueError:
                        pass
            i += 1
            continue

        i += 1

    result = {}
    if disp_values:
        result["disp_max"] = max(disp_values)
        result["disp_min"] = min(disp_values)
    if stress_values:
        result["stress_max"] = max(stress_values)
        result["stress_min"] = min(stress_values)

    return result


def extract_all_cases(test_dir: Path, output_path: Path) -> None:
    """批量提取所有测试用例的元数据和结果。"""
    cases: dict[str, dict] = {}

    # 查找所有 .inp 文件
    inp_files = sorted(test_dir.glob("*.inp"))
    print(f"找到 {len(inp_files)} 个 .inp 文件")

    for inp_file in inp_files:
        name = inp_file.stem
        ref_file = inp_file.with_suffix(".dat.ref")

        print(f"处理: {name}", end=" ... ")

        # 解析元数据
        try:
            meta = parse_inp_metadata(inp_file)
        except Exception as e:
            print(f"元数据解析失败: {e}")
            continue

        # 解析参考结果
        if ref_file.exists():
            try:
                results = parse_dat_ref(ref_file)
                meta.expected_disp_max = results.get("disp_max")
                meta.expected_disp_min = results.get("disp_min")
                meta.expected_stress_max = results.get("stress_max")
                meta.expected_stress_min = results.get("stress_min")
                meta.ref_path = str(ref_file)
            except Exception as e:
                print(f"结果解析失败: {e}")
        else:
            print("无参考文件 ", end="")

        # 存储
        cases[name] = meta.to_dict()
        print("完成")

    # 写入 JSON
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2, ensure_ascii=False)

    print(f"\n已写入 {len(cases)} 个案例到 {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    test_dir = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not test_dir.exists():
        print(f"错误: 目录不存在 {test_dir}")
        sys.exit(1)

    extract_all_cases(test_dir, output_path)
