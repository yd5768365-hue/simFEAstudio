"""
PDF 仿真报告生成器

功能：
  - 解析 .frd 文件，提取位移/应力统计
  - 从 .inp 文件读取材料属性（弹性模量、屈服强度）
  - 渲染位移云图 + Von Mises 应力云图（PyVista 截图）
  - 计算安全系数
  - 生成专业 PDF 报告（带云图、数值摘要）

依赖：weasyprint (pip install cae-cli[report])
"""
from __future__ import annotations

import logging
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from cae_preflight_lib.inp import InpModifier
from cae_preflight_lib.viewer.frd_parser import FrdData, parse_frd
from cae_preflight_lib.viewer.pyvista_renderer import render_displacement, render_von_mises
from cae_preflight_lib.viewer.vtk_export import frd_to_vtu

log = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# 数据结构
# ------------------------------------------------------------------ #

@dataclass
class MaterialProps:
    """材料属性。"""
    name: str = "未知材料"
    elastic_modulus: float = 210_000.0  # MPa
    poissons_ratio: float = 0.3
    yield_strength: float = 250.0  # MPa（默认钢材）


@dataclass
class ReportStats:
    """报告数值摘要。"""
    job_name: str = ""
    node_count: int = 0
    element_count: int = 0
    solve_time: str = ""

    max_displacement: float = 0.0  # mm
    max_displacement_node: int = 0
    max_displacement_unit: str = "mm"

    max_stress: float = 0.0  # MPa
    max_stress_element: int = 0
    stress_component: str = "Von Mises"

    safety_factor: float = 0.0
    utilization_ratio: float = 0.0  # 应力/屈服强度

    material: Optional[MaterialProps] = None

    model_bounds: tuple = ()  # (xmin, xmax, ymin, ymax, zmin, zmax)

    def model_size(self) -> str:
        """模型尺寸字符串。"""
        if not self.model_bounds or len(self.model_bounds) < 6:
            return "—"
        x, x2, y, y2, z, z2 = self.model_bounds
        return f"X: {x:.1f}~{x2:.1f}  Y: {y:.1f}~{y2:.1f}  Z: {z:.1f}~{z2:.1f}"


# ------------------------------------------------------------------ #
# 报告生成器
# ------------------------------------------------------------------ #

class PdfReportGenerator:
    """
    PDF 仿真报告生成器。

    Usage:
        gen = PdfReportGenerator(results_dir=Path("results/"))
        gen.set_inp_file(Path("model.inp"))          # 可选
        gen.set_yield_strength(350.0)                 # 可选覆盖
        gen.render_clouds()                           # 渲染云图
        output_path = gen.generate(Path("report.pdf"))
    """

    def __init__(
        self,
        results_dir: Path,
        *,
        job_name: str = "",
        solve_time: str = "",
    ):
        self.results_dir = Path(results_dir)
        self.job_name = job_name
        self.solve_time = solve_time

        self._frd_data: Optional[FrdData] = None
        self._inp_file: Optional[Path] = None
        self._yield_strength_override: Optional[float] = None
        self._material: Optional[MaterialProps] = None
        self._stats: Optional[ReportStats] = None

        self._disp_cloud_path: Optional[Path] = None
        self._vm_cloud_path: Optional[Path] = None
        self._temp_dir: Optional[Path] = None

    # ------------------------------------------------------------------ #
    # 配置
    # ------------------------------------------------------------------ #

    def set_inp_file(self, inp_file: Path) -> None:
        """设置 INP 文件路径（用于读取材料属性）。"""
        self._inp_file = Path(inp_file)
        self._material = self._parse_material(self._inp_file)

    def set_yield_strength(self, yield_strength: float) -> None:
        """手动设置屈服强度（MPa），覆盖 INP 文件的值。"""
        self._yield_strength_override = yield_strength
        if self._material:
            self._material.yield_strength = yield_strength

    # ------------------------------------------------------------------ #
    # 公共流程
    # ------------------------------------------------------------------ #

    def render_clouds(self, scale_factor: float = 50.0) -> "PdfReportGenerator":
        """
        渲染位移云图和应力云图（保存到临时目录）。

        Args:
            scale_factor: 变形放大倍数，默认 50

        Returns:
            self（链式调用）
        """
        self._temp_dir = Path(tempfile.mkdtemp(prefix="cae_report_"))

        # 找 FRD 文件
        frd_file = self._find_frd()
        if not frd_file:
            log.warning("未找到 .frd 文件，跳过云图渲染")
            return self

        # 转为 VTU
        try:
            vtu_result = frd_to_vtu(frd_file, self._temp_dir)
            if not vtu_result.success:
                log.warning(f"VTU 转换失败: {vtu_result.error}，跳过云图渲染")
                return self
            vtu_path = vtu_result.vtu_file
            if not vtu_path:
                log.warning("VTU 转换返回路径为空，跳过云图渲染")
                return self
        except Exception as exc:
            log.warning(f"VTU 转换失败: {exc}，跳过云图渲染")
            return self

        # 渲染位移云图
        self._disp_cloud_path = self._temp_dir / "disp_cloud.png"
        res = render_displacement(
            vtu_path,
            self._disp_cloud_path,
            scale_factor=scale_factor,
        )
        if not res.success:
            log.warning(f"位移云图渲染失败: {res.error}")
            self._disp_cloud_path = None

        # 渲染 Von Mises 应力云图
        self._vm_cloud_path = self._temp_dir / "vm_cloud.png"
        res = render_von_mises(vtu_path, self._vm_cloud_path)
        if not res.success:
            log.warning(f"Von Mises 应力云图渲染失败: {res.error}")
            self._vm_cloud_path = None

        return self

    def generate(self, output_path: Path) -> Path:
        """
        生成 PDF 报告。

        Args:
            output_path: 输出 .pdf 路径

        Returns:
            输出文件路径
        """
        try:
            from weasyprint import HTML
        except ImportError:
            raise RuntimeError(
                "PDF 生成需要 weasyprint，请运行: pip install cae-cli[report]"
            )

        # 提取统计信息
        self._stats = self._extract_stats()

        # 生成 HTML
        html_content = self._build_html()

        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 写入 PDF
        html_obj = HTML(string=html_content, base_url=str(self._temp_dir or "."))
        html_obj.write_pdf(target=str(output_path))

        log.info(f"PDF 报告已生成: {output_path}")
        return output_path

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #

    def _find_frd(self) -> Optional[Path]:
        """查找 FRD 文件。"""
        frd_files = sorted(self.results_dir.glob("*.frd"))
        return frd_files[0] if frd_files else None

    def _parse_material(self, inp_file: Path) -> MaterialProps:
        """从 INP 文件解析材料属性。"""
        mat = MaterialProps()
        if not inp_file.exists():
            return mat

        try:
            mod = InpModifier(inp_file)

            # 找材料名称
            mat_block = mod.find_block(keyword="*MATERIAL")
            if mat_block:
                mat.name = mat_block.get_param("NAME") or "未知材料"

            # 找弹性模量
            if mat_block:
                elastic_block = mod.find_block(keyword="*ELASTIC", name=mat.name)
                if elastic_block and elastic_block.data_lines:
                    # 第一行第一列是弹性模量
                    numbers = re.findall(
                        r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?",
                        elastic_block.data_lines[0],
                    )
                    if numbers:
                        val = float(numbers[0])
                        # 判断单位：>1e6 认为是 MPa，否则认为是 GPa
                        if val > 1e6:
                            mat.elastic_modulus = val
                        else:
                            mat.elastic_modulus = val * 1000.0  # GPa → MPa

                    if len(numbers) > 1:
                        mat.poissons_ratio = float(numbers[1])

            # 屈服强度（从 *PLASTIC 或默认值）
            plastic_block = mod.find_block(keyword="*PLASTIC", name=mat.name)
            if plastic_block and plastic_block.data_lines:
                numbers = re.findall(
                    r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?",
                    plastic_block.data_lines[0],
                )
                if numbers:
                    mat.yield_strength = float(numbers[0])

        except Exception as exc:
            log.warning(f"INP 材料解析失败: {exc}")

        # 覆盖值
        if self._yield_strength_override is not None:
            mat.yield_strength = self._yield_strength_override

        return mat

    def _extract_stats(self) -> ReportStats:
        """从 FRD 数据提取统计信息。"""
        frd_file = self._find_frd()
        stats = ReportStats(
            job_name=self.job_name or (frd_file.stem if frd_file else "未命名"),
            solve_time=self.solve_time,
            material=self._material,
        )

        if not frd_file:
            return stats

        try:
            self._frd_data = parse_frd(frd_file)
            frd = self._frd_data
        except Exception as exc:
            log.warning(f"FRD 解析失败: {exc}")
            return stats

        # 节点/单元数
        stats.node_count = frd.node_count
        stats.element_count = frd.element_count

        # 模型边界
        if frd.nodes and frd.nodes.coords:
            xs = [c[0] for c in frd.nodes.coords]
            ys = [c[1] for c in frd.nodes.coords]
            zs = [c[2] for c in frd.nodes.coords]
            if xs and ys and zs:
                stats.model_bounds = (
                    min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)
                )

        # 位移
        disp_result = frd.get_result("DISP")
        if disp_result and disp_result.values:
            all_disps = []
            for i, node_id in enumerate(disp_result.node_ids):
                vals = disp_result.values[i]
                if vals and len(vals) >= 3:
                    mag = sum(v ** 2 for v in vals[:3]) ** 0.5
                elif vals:
                    mag = abs(vals[0])
                else:
                    mag = 0.0
                all_disps.append((node_id, mag))

            if all_disps:
                max_node, max_disp = max(all_disps, key=lambda x: x[1])
                stats.max_displacement = max_disp
                stats.max_displacement_node = max_node

        # 应力（Von Mises）
        stress_result = frd.get_result("STRESS")
        if stress_result and stress_result.values:
            max_vm = 0.0
            max_vm_elem = 0
            for i, vals in enumerate(stress_result.values):
                if not vals:
                    continue
                # 第4个分量是 Von Mises（CalculiX 输出格式）
                if len(vals) >= 4:
                    vm = abs(vals[3])
                else:
                    vm = max(abs(v) for v in vals)
                if vm > max_vm:
                    max_vm = vm
                    max_vm_elem = stress_result.node_ids[i]

            stats.max_stress = max_vm
            stats.max_stress_element = max_vm_elem

        # 安全系数
        mat = self._material
        if mat and stats.max_stress > 0:
            stats.safety_factor = mat.yield_strength / stats.max_stress
            stats.utilization_ratio = stats.max_stress / mat.yield_strength

        return stats

    def _build_html(self) -> str:
        """构建 HTML 内容（用于 PDF 转换）。"""
        stats = self._stats or ReportStats()
        mat = stats.material or MaterialProps()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        disp_cloud_b64 = self._img_to_base64(self._disp_cloud_path) if self._disp_cloud_path else None
        vm_cloud_b64 = self._img_to_base64(self._vm_cloud_path) if self._vm_cloud_path else None

        # 安全系数颜色
        if stats.safety_factor >= 1.5:
            sf_color = "#44dd88"
            sf_label = "安全"
        elif stats.safety_factor >= 1.0:
            sf_color = "#ffaa44"
            sf_label = "警告"
        else:
            sf_color = "#ff6666"
            sf_label = "危险"

        # 云图 HTML
        disp_cloud_html = (
            f'<img src="data:image/png;base64,{disp_cloud_b64}" '
            f'alt="位移云图" style="width:100%;border-radius:8px;"/>'
            if disp_cloud_b64
            else '<div class="no-image">（未生成位移云图）</div>'
        )

        vm_cloud_html = (
            f'<img src="data:image/png;base64,{vm_cloud_b64}" '
            f'alt="Von Mises 应力云图" style="width:100%;border-radius:8px;"/>'
            if vm_cloud_b64
            else '<div class="no-image">（未生成应力云图）</div>'
        )

        # 位移值格式化
        max_disp = stats.max_displacement
        if max_disp < 1.0:
            disp_str = f"{max_disp * 1000:.3f} mm"
        elif max_disp < 10.0:
            disp_str = f"{max_disp:.4f} mm"
        else:
            disp_str = f"{max_disp:.2f} mm"

        return f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<title>CAE 仿真报告 — {stats.job_name}</title>
<style>
  @page {{
    size: A4;
    margin: 18mm 15mm 18mm 15mm;
    @bottom-center {{
      content: "cae-cli 仿真报告  ·  第 " counter(page) " 页";
      font-size: 9pt;
      color: #888;
    }}
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    font-size: 11pt;
    color: #1a1a2e;
    line-height: 1.6;
    background: #fff;
  }}

  /* ---- 封面标题区 ---- */
  .report-header {{
    background: linear-gradient(135deg, #1a1a30 0%, #2a3a5a 100%);
    color: white;
    padding: 28px 32px 22px;
    border-radius: 12px 12px 0 0;
    margin-bottom: 24px;
  }}
  .report-header h1 {{
    font-size: 22pt;
    font-weight: 700;
    letter-spacing: 0.05em;
    margin-bottom: 6px;
    color: #7ec8e3;
  }}
  .report-header .meta {{
    font-size: 10pt;
    color: rgba(255,255,255,0.65);
    display: flex;
    gap: 24px;
    flex-wrap: wrap;
  }}
  .report-header .meta span {{
    display: flex;
    align-items: center;
    gap: 4px;
  }}

  /* ---- 统计卡片 ---- */
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-bottom: 24px;
  }}
  .stat-card {{
    background: #f5f7fa;
    border: 1px solid #e0e4ec;
    border-radius: 10px;
    padding: 14px 16px;
    border-left: 4px solid #4488ff;
  }}
  .stat-card.danger {{ border-left-color: #ff6666; background: #fff5f5; }}
  .stat-card.warning {{ border-left-color: #ffaa44; background: #fffaf0; }}
  .stat-card.success {{ border-left-color: #44dd88; background: #f0fff5; }}
  .stat-card .label {{
    font-size: 8.5pt;
    color: #7070a0;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 4px;
  }}
  .stat-card .value {{
    font-size: 17pt;
    font-weight: 700;
    color: #1a1a2e;
    line-height: 1.2;
  }}
  .stat-card .sub {{
    font-size: 8pt;
    color: #7070a0;
    margin-top: 2px;
  }}

  /* ---- 分隔标题 ---- */
  h2 {{
    font-size: 13pt;
    font-weight: 600;
    color: #1a1a2e;
    border-bottom: 2px solid #4488ff;
    padding-bottom: 6px;
    margin: 24px 0 14px;
  }}

  /* ---- 云图 ---- */
  .cloud-section {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 24px;
  }}
  .cloud-card {{
    background: #f9fafc;
    border: 1px solid #e0e4ec;
    border-radius: 10px;
    overflow: hidden;
  }}
  .cloud-card .caption {{
    padding: 10px 14px;
    font-size: 10pt;
    color: #555;
    background: #f0f2f7;
    border-top: 1px solid #e0e4ec;
  }}
  .cloud-card .caption strong {{
    color: #1a1a2e;
    display: block;
    margin-bottom: 2px;
  }}
  .no-image {{
    height: 180px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #aaa;
    background: #f5f7fa;
    border-radius: 8px;
    font-size: 10pt;
  }}

  /* ---- 详细数据表 ---- */
  .data-table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 24px;
    font-size: 10pt;
  }}
  .data-table th {{
    background: #2a3a5a;
    color: white;
    padding: 9px 14px;
    text-align: left;
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}
  .data-table td {{
    padding: 8px 14px;
    border-bottom: 1px solid #e8ecf0;
  }}
  .data-table tr:nth-child(even) td {{
    background: #f8f9fb;
  }}
  .data-table .num {{
    text-align: right;
    font-feature-settings: "tnum";
    font-variant-numeric: tabular-nums;
  }}
  .data-table .unit {{
    color: #888;
    font-size: 9pt;
  }}
  .data-table .tag {{
    display: inline-block;
    padding: 1px 8px;
    border-radius: 10px;
    font-size: 9pt;
    font-weight: 600;
  }}
  .tag-safe {{ background: #d4f5e1; color: #1a8a40; }}
  .tag-warn {{ background: #fff3d0; color: #b07000; }}
  .tag-danger {{ background: #ffd8d8; color: #c02020; }}

  /* ---- 材料卡片 ---- */
  .material-card {{
    background: #f0f5ff;
    border: 1px solid #c0d0f0;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 24px;
  }}
  .material-card h3 {{
    font-size: 11pt;
    color: #2a4a8a;
    margin-bottom: 8px;
  }}
  .material-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
  }}
  .material-item .m-label {{
    font-size: 8pt;
    color: #7070a0;
    text-transform: uppercase;
  }}
  .material-item .m-value {{
    font-size: 12pt;
    font-weight: 600;
    color: #1a1a2e;
  }}
  .material-item .m-unit {{
    font-size: 9pt;
    color: #888;
  }}

  /* ---- 页脚 ---- */
  .report-footer {{
    margin-top: 30px;
    padding-top: 14px;
    border-top: 1px solid #e0e4ec;
    font-size: 9pt;
    color: #aaa;
    text-align: center;
  }}
</style>
</head>
<body>

<!-- 标题区 -->
<div class="report-header">
  <h1>CAE 仿真报告</h1>
  <div class="meta">
    <span>📁 {stats.job_name}</span>
    <span>📅 {now}</span>
    <span>⚙️ CalculiX 求解器</span>
    <span>🔢 {stats.node_count:,} 节点  ·  {stats.element_count:,} 单元</span>
    {"<span>⏱ " + stats.solve_time + "</span>" if stats.solve_time else ""}
  </div>
</div>

<!-- 关键指标 -->
<div class="stats-grid">
  <div class="stat-card">
    <div class="label">最大位移</div>
    <div class="value">{disp_str}</div>
    <div class="sub">节点 {stats.max_displacement_node}</div>
  </div>
  <div class="stat-card">
    <div class="label">最大 Von Mises 应力</div>
    <div class="value">{stats.max_stress:.1f} <span class="unit">MPa</span></div>
    <div class="sub">单元 {stats.max_stress_element}</div>
  </div>
  <div class="stat-card {'success' if stats.safety_factor >= 1.5 else 'warning' if stats.safety_factor >= 1.0 else 'danger'}">
    <div class="label">安全系数</div>
    <div class="value" style="color:{sf_color}">{stats.safety_factor:.2f}</div>
    <div class="sub">{sf_label}（材料: {mat.name}）</div>
  </div>
  <div class="stat-card">
    <div class="label">屈服强度</div>
    <div class="value">{mat.yield_strength:.0f} <span class="unit">MPa</span></div>
    <div class="sub">E = {mat.elastic_modulus:,.0f} MPa</div>
  </div>
</div>

<!-- 云图 -->
<h2>📊 仿真结果云图</h2>
<div class="cloud-section">
  <div class="cloud-card">
    {disp_cloud_html}
    <div class="caption">
      <strong>位移云图（变形放大 {50}x）</strong>
      总最大位移：{disp_str}
    </div>
  </div>
  <div class="cloud-card">
    {vm_cloud_html}
    <div class="caption">
      <strong>Von Mises 等效应力云图</strong>
      最大等效应力：{stats.max_stress:.1f} MPa
    </div>
  </div>
</div>

<!-- 材料属性 -->
<h2>🏗 材料属性</h2>
<div class="material-card">
  <h3>材料名称：{mat.name}</h3>
  <div class="material-grid">
    <div class="material-item">
      <div class="m-label">弹性模量 E</div>
      <div class="m-value">{mat.elastic_modulus:,.0f}</div>
      <div class="m-unit">MPa</div>
    </div>
    <div class="material-item">
      <div class="m-label">屈服强度 σ_y</div>
      <div class="m-value">{mat.yield_strength:.0f}</div>
      <div class="m-unit">MPa</div>
    </div>
    <div class="material-item">
      <div class="m-label">泊松比 ν</div>
      <div class="m-value">{mat.poissons_ratio:.2f}</div>
      <div class="m-unit">—</div>
    </div>
  </div>
</div>

<!-- 详细数据 -->
<h2>📋 完整数值摘要</h2>
<table class="data-table">
  <thead>
    <tr>
      <th>项目</th>
      <th>数值</th>
      <th>单位</th>
      <th>位置/说明</th>
      <th>状态</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>最大位移（幅值）</td>
      <td class="num">{stats.max_displacement:.4f}</td>
      <td class="unit">mm</td>
      <td>节点 #{stats.max_displacement_node}</td>
      <td>—</td>
    </tr>
    <tr>
      <td>最大 Von Mises 应力</td>
      <td class="num">{stats.max_stress:.2f}</td>
      <td class="unit">MPa</td>
      <td>单元 #{stats.max_stress_element}</td>
      <td>—</td>
    </tr>
    <tr>
      <td>材料屈服强度</td>
      <td class="num">{mat.yield_strength:.1f}</td>
      <td class="unit">MPa</td>
      <td>{mat.name}</td>
      <td>—</td>
    </tr>
    <tr>
      <td>安全系数</td>
      <td class="num">{stats.safety_factor:.3f}</td>
      <td class="unit">—</td>
      <td>屈服强度 / 最大应力</td>
      <td>
        <span class="tag {'tag-safe' if stats.safety_factor >= 1.5 else 'tag-warn' if stats.safety_factor >= 1.0 else 'tag-danger'}">
          {sf_label}
        </span>
      </td>
    </tr>
    <tr>
      <td>应力利用率</td>
      <td class="num">{stats.utilization_ratio * 100:.1f}</td>
      <td class="unit">%</td>
      <td>最大应力 / 屈服强度</td>
      <td>—</td>
    </tr>
    <tr>
      <td>模型尺寸</td>
      <td colspan="4">{stats.model_size()}</td>
    </tr>
  </tbody>
</table>

<!-- 页脚 -->
<div class="report-footer">
  由 cae-cli 生成  ·  基于 CalculiX 求解器  ·  {now}
</div>

</body>
</html>
"""

    @staticmethod
    def _img_to_base64(img_path: Optional[Path]) -> Optional[str]:
        """将图片文件转为 base64 字符串。"""
        if not img_path or not img_path.exists():
            return None
        import base64
        return base64.b64encode(img_path.read_bytes()).decode("ascii")


# ------------------------------------------------------------------ #
# 便捷入口
# ------------------------------------------------------------------ #

def generate_pdf_report(
    results_dir: Path,
    output_path: Path,
    *,
    inp_file: Optional[Path] = None,
    job_name: str = "",
    solve_time: str = "",
    yield_strength: Optional[float] = None,
    scale_factor: float = 50.0,
) -> Path:
    """
    一键生成 PDF 仿真报告。

    Args:
        results_dir: 包含 .frd 文件的结果目录
        output_path: 输出 .pdf 文件路径
        inp_file: 可选，.inp 文件路径（读取材料属性）
        job_name: 工况名称
        solve_time: 求解耗时字符串
        yield_strength: 手动指定屈服强度（MPa），优先级高于 inp_file
        scale_factor: 变形放大倍数

    Returns:
        生成的 PDF 文件路径
    """
    gen = PdfReportGenerator(
        results_dir=results_dir,
        job_name=job_name,
        solve_time=solve_time,
    )
    if inp_file:
        gen.set_inp_file(inp_file)
    if yield_strength is not None:
        gen.set_yield_strength(yield_strength)

    gen.render_clouds(scale_factor=scale_factor)
    return gen.generate(output_path)
