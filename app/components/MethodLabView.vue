<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import type { SimfeaClient } from '@/api'
import { createSimfeaClient } from '@/api'
import { useMethodLab } from '@/composables/useMethodLab'

const props = defineProps<{ apiBaseUrl: string }>()
const emit = defineEmits<{ back: [] }>()

type MethodSectionId = 'overview' | 'cae-ladder' | 'evidence' | 'assistant' | 'roadmap'

interface MethodSection {
  id: MethodSectionId
  title: string
  summary: string
}

const sections: MethodSection[] = [
  { id: 'overview', title: '方法定位', summary: '从真实系统进入，重建学习者自己的最小理解闭环。' },
  { id: 'cae-ladder', title: 'FE / CAE 入口阶梯', summary: '用三层入口控制真实系统带来的认知负荷。' },
  { id: 'evidence', title: '案例证据栈', summary: '判断一个案例是否真正可复盘。' },
  { id: 'assistant', title: 'AI 助手协议', summary: '让 AI 保持引导者角色，而不是代学执行者。' },
  { id: 'roadmap', title: 'CAE 案例路线', summary: '把方法逐步接入 simFEA Studio 的真实仿真工作流。' },
]

const activeSectionId = ref<MethodSectionId>('overview')
const activeSection = computed(
  () => sections.find((section) => section.id === activeSectionId.value) ?? sections[0]
)

const api: SimfeaClient = createSimfeaClient(props.apiBaseUrl, () => {})
const { cases, loading, ladderLevels, caseEvidence, methodLabStats, roadmapCases, fetchCases } =
  useMethodLab(api)

onMounted(fetchCases)
onActivated(fetchCases)

const evidenceLabels = ['运行证明', '失败证据', '系统结构图', '单路径调用链', '最小闭环', '差异比较']

const gates = [
  {
    name: '证据门',
    body: '没有证据面，AI 只能继续提问，不能直接诊断。',
    app: '在 Benchmark Lab 的对比表中，每个方法都需要附上运行日志、输入文件和结果截图作为证据。未提交证据的方法行显示警告标记。',
  },
  {
    name: '预测门',
    body: '解释之前先让学习者给出预测或假设。',
    app: '在查看某个案例的解析解之前，Composer 的作业面板会提示你先填入自己对位移 / 应力的估计值，然后才能查看参考答案。',
  },
  {
    name: '梯度帮助门',
    body: '帮助从问题、提示、定向提示、局部模板逐级升级。',
    app: 'AI 助手在回答 CAE 问题时，会先反问一个引导性问题。只有在你明确请求时，才会给出直接答案或代码模板。',
  },
  {
    name: '所有权门',
    body: '运行、验证、编码和最终判断默认属于学习者。',
    app: '所有求解器运行需要你手动点击"提交"。AI 可以建议参数，但不能替你提交作业。运行结果是否正确由你判断，AI 只提供参考区间。',
  },
  {
    name: '停止门',
    body: '达到当前目标后转入比较和缺口分析。',
    app: '完成一个案例后，学习报告会自动生成对比分析，并标出与其他方法的差异。此时 AI 停止追问，转入下一案例或等待你发起新问题。',
  },
  {
    name: '自审门',
    body: 'AI 输出前检查自己是否越界替跑、替写、替判断。',
    app: 'AI 在每次回答后会自动标注"此回答属于：解释/建议/模板/判断"，让你一眼看出 AI 是否越权。',
  },
]

const expandedGates = ref<Set<string>>(new Set())

function toggleGate(name: string) {
  if (expandedGates.value.has(name)) {
    expandedGates.value.delete(name)
  } else {
    expandedGates.value.add(name)
  }
}

function evidenceIcon(val: boolean | null): string {
  if (val === true) return '✓'
  if (val === false) return '—'
  return '?'
}

function evidenceClass(val: boolean | null): string {
  if (val === true) return 'ev-check'
  if (val === false) return 'ev-miss'
  return 'ev-unknown'
}
</script>

<template>
  <div class="mlv">
    <div class="mlv-top">
      <button type="button" class="mlv-back" @click="emit('back')">
        <svg width="14" height="14" viewBox="0 0 16 16">
          <path d="M10 3L5 8l5 5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" />
        </svg>
      </button>
      <span class="mlv-title">方法</span>
      <span class="mlv-current">{{ activeSection.title }}</span>
      <span class="mlv-spacer" />
      <span class="mlv-badge">From 1 to 0</span>
    </div>

    <div class="mlv-body">
      <nav class="mlv-sidebar" aria-label="方法文档">
        <div class="mlv-sidebar-head">Method Lab</div>
        <button
          v-for="section in sections"
          :key="section.id"
          type="button"
          class="mlv-file-btn"
          :class="{ active: activeSectionId === section.id }"
          @click="activeSectionId = section.id"
        >
          <span>{{ section.title }}</span>
          <small>{{ section.summary }}</small>
        </button>
      </nav>

      <main class="mlv-main">
        <!-- Loading -->
        <div v-if="loading && cases.length === 0" class="mlv-loading">
          <span class="mlv-spinner" />
          <span>加载基准案例数据…</span>
        </div>

        <!-- Empty -->
        <div v-else-if="!loading && cases.length === 0" class="mlv-empty">
          <p>暂无可用的基准案例数据。</p>
          <p class="mlv-empty-hint">在 <code>learning/benchmarks/</code> 目录添加案例后刷新。</p>
        </div>

        <!-- ====== Overview ====== -->
        <article v-else-if="activeSectionId === 'overview'" class="mlv-content">
          <h1>From 1 to 0 方法实验室</h1>
          <p>
            这个界面把 from-1-to-0-lab 接入 simFEA Studio。它不是普通说明页，而是 Method Lab 的入口：
            用来组织有限元、CAE、机械工程仿真工具链中的学习方法、案例证据和 AI 助手协议。
          </p>

          <blockquote>
            From 1 to 0 不是从基础知识线性推到实战，而是从一个真实、可观察的完整系统进入。
            学习者通过运行观察、失败记录、入口追踪和单路径调用链分析，最后重建一个由自己实现、
            可运行、可验证的最小闭环。
          </blockquote>

          <h2>当前基准案例概览</h2>
          <div class="mlv-stats-row">
            <div class="mlv-stat-card">
              <span class="mlv-stat-num">{{ methodLabStats.totalCases }}</span>
              <span class="mlv-stat-label">总案例</span>
            </div>
            <div class="mlv-stat-card">
              <span class="mlv-stat-num">{{ methodLabStats.casesWithProblems }}</span>
              <span class="mlv-stat-label">有问题描述</span>
            </div>
            <div class="mlv-stat-card">
              <span class="mlv-stat-num">{{ methodLabStats.casesWithResults }}</span>
              <span class="mlv-stat-label">有求解结果</span>
            </div>
            <div class="mlv-stat-card">
              <span class="mlv-stat-num">{{ methodLabStats.completionPercent }}%</span>
              <span class="mlv-stat-label">完成率</span>
              <div class="mlv-mini-bar">
                <div
                  class="mlv-mini-bar-fill"
                  :style="{ width: methodLabStats.completionPercent + '%' }"
                />
              </div>
            </div>
          </div>

          <div class="mlv-group-cards" v-if="methodLabStats.casesByGroup.length">
            <span
              v-for="g in methodLabStats.casesByGroup"
              :key="g.label"
              class="mlv-group-chip"
            >{{ g.label }} · {{ g.count }} 个</span>
          </div>

          <h2>仓库关系</h2>
          <pre>from-1-to-0-lab
→ Skill / framework / cases
→ Method Lab
→ Case Lab
→ AI Assistant
→ simFEA Studio</pre>

          <h2>当前定位</h2>
          <p>
            这个 Skill 的研究主场是机械工程，尤其是有限元、CAE、工程仿真工具链与 AI4CAE。
            OpenClaw 这类 AI Agent 案例可以用来验证方法，但长期案例积累会回到机械 / CAE 方向。
          </p>
        </article>

        <!-- ====== CAE Ladder ====== -->
        <article v-else-if="activeSectionId === 'cae-ladder'" class="mlv-content">
          <h1>FE / CAE 入口阶梯</h1>
          <p>
            有限元和 CAE 同时包含数学层、工程语义层和软件系统层。Method Lab 不主张新手直接读大型求解器源码，
            而是先选择一个可观察、可运行、可对比的真实算例作为整体锚点。
          </p>

          <div class="mlv-topic-list">
            <section v-for="lv in ladderLevels" :key="lv.level" class="mlv-ladder-card">
              <div class="mlv-ladder-head">
                <span class="mlv-ladder-badge" :class="`ladder-l${lv.level}`">L{{ lv.level }}</span>
                <strong>{{ lv.label }}</strong>
                <span class="mlv-ladder-count">
                  {{ lv.completeCases }}/{{ lv.totalCases }} 案例完备
                </span>
              </div>
              <p>{{ lv.body }}</p>

              <div v-if="lv.totalCases === 0" class="mlv-ladder-empty">
                暂无满足此层级条件的案例
              </div>
              <div v-else class="mlv-ladder-cases">
                <span
                  v-for="c in lv.cases"
                  :key="c.name"
                  class="mlv-ladder-case-chip"
                  :class="{ complete: c.complete, partial: !c.complete }"
                  :title="c.title"
                >
                  <span class="mlv-case-dot" :class="c.complete ? 'dot-green' : 'dot-amber'" />
                  {{ c.title }}
                </span>
              </div>

              <div class="mlv-ladder-bar">
                <div
                  class="mlv-ladder-bar-fill"
                  :class="`bar-l${lv.level}`"
                  :style="{ width: lv.totalCases > 0 ? (lv.completeCases / lv.totalCases * 100) + '%' : '0%' }"
                />
              </div>
            </section>
          </div>
        </article>

        <!-- ====== Evidence Stack ====== -->
        <article v-else-if="activeSectionId === 'evidence'" class="mlv-content">
          <h1>案例证据栈</h1>
          <p>
            最小闭环不是唯一证据，但通常是最强、最难伪造、最可检验的学习主证据。
            以下矩阵展示每个基准案例当前具备的证据类型。
            <span class="mlv-ev-legend">
              <span class="ev-check">✓</span> 确定具备
              <span class="ev-miss">—</span> 未检测到
              <span class="ev-unknown">?</span> 加载详情后检测
            </span>
          </p>

          <div class="mlv-ev-wrapper">
            <table class="mlv-ev-matrix">
              <thead>
                <tr>
                  <th class="mlv-ev-case-col">案例</th>
                  <th v-for="label in evidenceLabels" :key="label">{{ label }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="ce in caseEvidence" :key="ce.caseName">
                  <td class="mlv-ev-case-col">
                    <span class="mlv-ev-case-name">{{ ce.title }}</span>
                    <span class="mlv-ev-group-tag">{{ ce.group }}</span>
                  </td>
                  <td :class="evidenceClass(ce.evidence.runProof)">{{ evidenceIcon(ce.evidence.runProof) }}</td>
                  <td :class="evidenceClass(ce.evidence.failureRecord)">{{ evidenceIcon(ce.evidence.failureRecord) }}</td>
                  <td :class="evidenceClass(ce.evidence.systemDiagram)">{{ evidenceIcon(ce.evidence.systemDiagram) }}</td>
                  <td :class="evidenceClass(ce.evidence.singlePathCall)">{{ evidenceIcon(ce.evidence.singlePathCall) }}</td>
                  <td :class="evidenceClass(ce.evidence.minClosedLoop)">{{ evidenceIcon(ce.evidence.minClosedLoop) }}</td>
                  <td :class="evidenceClass(ce.evidence.diffComparison)">{{ evidenceIcon(ce.evidence.diffComparison) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <h2>评价问题</h2>
          <ul>
            <li>可观察吗？有没有命令、日志、输入输出、错误文本或结果文件。</li>
            <li>可归因吗？能否区分学习者动作和 AI 建议。</li>
            <li>可判别吗？学习者能否说明保留、删除和损失的能力。</li>
          </ul>
        </article>

        <!-- ====== AI Assistant ====== -->
        <article v-else-if="activeSectionId === 'assistant'" class="mlv-content">
          <h1>AI 助手协议</h1>
          <p>
            在 simFEA Studio 中，AI Assistant 不只是报错修复器。它是 CAE 学习教练和工程诊断助手，
            帮助学习者形成证据、假设、验证和最小闭环。
          </p>

          <div class="mlv-gate-list">
            <section
              v-for="gate in gates"
              :key="gate.name"
              class="mlv-gate-card"
              :class="{ expanded: expandedGates.has(gate.name) }"
            >
              <button type="button" class="mlv-gate-summary" @click="toggleGate(gate.name)">
                <strong>{{ gate.name }}</strong>
                <p>{{ gate.body }}</p>
                <svg
                  class="mlv-gate-chevron"
                  :class="{ open: expandedGates.has(gate.name) }"
                  width="12"
                  height="12"
                  viewBox="0 0 16 16"
                >
                  <path d="M5 5l3 3-3 3" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" />
                </svg>
              </button>
              <div v-if="expandedGates.has(gate.name)" class="mlv-gate-detail">
                <h4>在 Studio 中的应用</h4>
                <p>{{ gate.app }}</p>
              </div>
            </section>
          </div>

          <blockquote>
            AI 搜索、解释、比较与设计实验；学习者运行、验证、画图、编码和最终判断。
          </blockquote>
        </article>

        <!-- ====== Roadmap ====== -->
        <article v-else class="mlv-content">
          <h1>CAE 案例路线</h1>
          <p>
            OpenClaw 用来验证"从真实复杂系统拆出最小闭环"的通用方法。以下案例来自 Benchmark Lab，
            按类别和完成状态排列。
          </p>

          <div class="mlv-roadmap-list">
            <div
              v-for="rc in roadmapCases"
              :key="rc.name"
              class="mlv-roadmap-item"
              :class="{ complete: rc.complete }"
            >
              <div class="mlv-roadmap-left">
                <span class="mlv-roadmap-dot" :class="rc.complete ? 'dot-green' : 'dot-amber'" />
              </div>
              <div class="mlv-roadmap-body">
                <div class="mlv-roadmap-head">
                  <span class="mlv-roadmap-name">{{ rc.title }}</span>
                  <span class="mlv-roadmap-group">{{ rc.group }}</span>
                  <span class="mlv-roadmap-status" :class="rc.complete ? 'st-ready' : 'st-wip'">
                    {{ rc.complete ? '完备' : '进行中' }}
                  </span>
                </div>
                <div class="mlv-roadmap-steps">
                  <span class="mlv-roadmap-step" :class="{ done: rc.hasProblem }">
                    <span class="mlv-step-icon">{{ rc.hasProblem ? '✓' : '○' }}</span>
                    问题描述
                  </span>
                  <span class="mlv-roadmap-arrow">→</span>
                  <span class="mlv-roadmap-step" :class="{ done: rc.hasResults }">
                    <span class="mlv-step-icon">{{ rc.hasResults ? '✓' : '○' }}</span>
                    求解结果
                  </span>
                </div>
                <span class="mlv-roadmap-next">{{ rc.nextStep }}</span>
              </div>
            </div>
          </div>

          <h2>接入 simFEA Studio 的方式</h2>
          <p>
            每个 CAE 案例都应该能进入 Case Lab：展示案例目标、环境检查、运行命令、输入文件、求解日志、
            结果查看、Python 最小闭环、与原系统对比和反思记录。
          </p>
        </article>
      </main>
    </div>
  </div>
</template>

<style scoped>
/* ===== Layout ===== */
.mlv {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0 20px;
}

.mlv-top {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border-subtle);
  padding: 12px 0;
}

.mlv-back {
  padding: 2px;
  border: none;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
}

.mlv-back:hover {
  color: var(--text-body);
}

.mlv-title {
  color: var(--text-heading);
  font-size: 0.85rem;
  font-weight: 600;
}

.mlv-current {
  color: var(--text-dim);
  font-size: 0.72rem;
}

.mlv-spacer {
  flex: 1;
}

.mlv-badge {
  border: 1px solid var(--accent-border);
  border-radius: 999px;
  padding: 4px 10px;
  background: var(--accent-glow);
  color: var(--accent-hover);
  font-size: 0.7rem;
  font-weight: 800;
}

.mlv-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

/* ===== Sidebar ===== */
.mlv-sidebar {
  width: 230px;
  flex-shrink: 0;
  overflow-y: auto;
  border-right: 1px solid var(--border-subtle);
  padding: 10px 8px;
}

.mlv-sidebar-head {
  padding: 0 6px 8px;
  color: var(--text-dim);
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.mlv-file-btn {
  display: grid;
  gap: 3px;
  width: 100%;
  min-height: 0;
  border: none;
  border-radius: 4px;
  padding: 8px 7px;
  background: none;
  color: var(--text-body);
  text-align: left;
  cursor: pointer;
}

.mlv-file-btn:hover {
  background: rgba(255, 255, 255, 0.03);
}

.mlv-file-btn.active {
  background: var(--accent-glow);
  color: var(--accent);
}

.mlv-file-btn span {
  font-size: 0.76rem;
  font-weight: 700;
}

.mlv-file-btn small {
  color: var(--text-dim);
  font-size: 0.66rem;
  line-height: 1.35;
}

/* ===== Main ===== */
.mlv-main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 20px 24px;
}

.mlv-content {
  max-width: 960px;
  margin: 0 auto;
  padding-bottom: 60px;
  color: var(--text-body);
  font-size: 0.85rem;
  line-height: 1.85;
}

.mlv-content h1 {
  margin: 0 0 16px;
  border-bottom: 1px solid var(--border-default);
  padding-bottom: 10px;
  color: var(--text-heading);
  font-size: 1.4rem;
  font-weight: 800;
}

.mlv-content h2 {
  margin: 32px 0 12px;
  border-left: 3px solid var(--accent);
  padding-left: 12px;
  color: var(--text-heading);
  font-size: 1.12rem;
  font-weight: 700;
}

.mlv-content h4 {
  margin: 0 0 6px;
  color: var(--text-heading);
  font-size: 0.88rem;
  font-weight: 700;
}

.mlv-content p,
.mlv-content li {
  color: var(--text-body);
}

.mlv-content blockquote {
  margin: 16px 0;
  border-left: 3px solid var(--accent);
  border-radius: 0 8px 8px 0;
  padding: 12px 18px;
  background: var(--accent-glow);
  color: var(--text-muted);
}

.mlv-content pre {
  overflow-x: auto;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 16px 20px;
  background: var(--bg-input);
  color: var(--text-body);
  font-family: var(--font-mono);
  font-size: 0.78rem;
  line-height: 1.65;
}

.mlv-content ul {
  padding-left: 20px;
}

.mlv-content ul li {
  margin: 4px 0;
}

/* ===== Loading & Empty ===== */
.mlv-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 0;
  color: var(--text-muted);
  font-size: 0.82rem;
}

.mlv-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border-subtle);
  border-top-color: var(--accent-hover);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.mlv-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 60px 0;
  border: 1px dashed var(--border-default);
  border-radius: 8px;
  color: var(--text-muted);
  font-size: 0.82rem;
}

.mlv-empty-hint {
  font-size: 0.72rem;
  color: var(--text-dim);
}

.mlv-empty-hint code {
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--bg-input);
  font-family: var(--font-mono);
  font-size: 0.7rem;
}

/* ===== Stats Cards ===== */
.mlv-stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-top: 8px;
}

.mlv-stat-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  border: 1px solid var(--border-default);
  border-left: 3px solid var(--accent);
  border-radius: 8px;
  padding: 14px 16px;
  background:
    linear-gradient(180deg, rgba(31, 38, 50, 0.96), rgba(17, 21, 30, 0.96)),
    repeating-linear-gradient(90deg, rgba(255,255,255,0.035) 0 1px, transparent 1px 34px);
}

.mlv-stat-num {
  color: var(--accent-hover);
  font-size: 1.5rem;
  font-weight: 850;
  line-height: 1.2;
}

.mlv-stat-label {
  color: var(--text-dim);
  font-size: 0.7rem;
  font-weight: 600;
}

.mlv-mini-bar {
  width: 100%;
  height: 4px;
  border-radius: 2px;
  background: var(--border-subtle);
  margin-top: 6px;
  overflow: hidden;
}

.mlv-mini-bar-fill {
  height: 100%;
  border-radius: 2px;
  background: var(--accent);
  transition: width var(--transition-normal);
}

/* ===== Group Chips ===== */
.mlv-group-cards {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}

.mlv-group-chip {
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  padding: 4px 14px;
  background: var(--bg-card);
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 600;
}

/* ===== CAE Ladder ===== */
.mlv-topic-list {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}

.mlv-ladder-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 16px 18px;
  background:
    linear-gradient(180deg, rgba(31, 38, 50, 0.96), rgba(17, 21, 30, 0.96)),
    repeating-linear-gradient(90deg, rgba(255,255,255,0.035) 0 1px, transparent 1px 34px);
}

.mlv-ladder-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.mlv-ladder-badge {
  border-radius: 999px;
  padding: 2px 9px;
  color: #fff;
  font-size: 0.66rem;
  font-weight: 850;
}

.ladder-l1 { background: var(--accent-blue); }
.ladder-l2 { background: var(--accent); }
.ladder-l3 { background: var(--amber-strong); }

.mlv-ladder-card strong {
  color: var(--text-heading);
  font-size: 0.92rem;
}

.mlv-ladder-count {
  margin-left: auto;
  color: var(--text-dim);
  font-size: 0.7rem;
  font-weight: 600;
}

.mlv-ladder-card p {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.82rem;
  line-height: 1.6;
}

.mlv-ladder-empty {
  padding: 10px 0;
  color: var(--text-dim);
  font-size: 0.76rem;
  font-style: italic;
}

.mlv-ladder-cases {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.mlv-ladder-case-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 0.7rem;
  font-weight: 600;
  border: 1px solid var(--border-subtle);
  color: var(--text-body);
}

.mlv-ladder-case-chip.complete {
  border-color: rgba(46, 204, 113, 0.3);
  background: rgba(46, 204, 113, 0.08);
}

.mlv-ladder-case-chip.partial {
  border-color: rgba(245, 166, 35, 0.25);
  background: rgba(245, 166, 35, 0.06);
}

.mlv-case-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-green { background: var(--green); box-shadow: 0 0 4px var(--green-soft); }
.dot-amber { background: var(--amber); box-shadow: 0 0 4px var(--amber-soft); }

.mlv-ladder-bar {
  width: 100%;
  height: 4px;
  border-radius: 2px;
  background: var(--border-subtle);
  overflow: hidden;
}

.mlv-ladder-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width var(--transition-normal);
}

.bar-l1 { background: var(--accent-blue); }
.bar-l2 { background: var(--accent); }
.bar-l3 { background: var(--amber); }

/* ===== Evidence Matrix ===== */
.mlv-ev-legend {
  display: inline-flex;
  gap: 10px;
  margin-left: 16px;
  font-size: 0.7rem;
  color: var(--text-dim);
}

.mlv-ev-wrapper {
  overflow-x: auto;
  margin: 14px 0 20px;
}

.mlv-ev-matrix {
  width: 100%;
  border: 1px solid var(--border-default);
  border-collapse: collapse;
  font-size: 0.78rem;
}

.mlv-ev-matrix th {
  border-bottom: 2px solid var(--border-strong);
  padding: 10px 12px;
  background: var(--bg-panel);
  color: var(--text-muted);
  text-align: center;
  font-size: 0.7rem;
  font-weight: 700;
  white-space: nowrap;
}

.mlv-ev-matrix td {
  border-bottom: 1px solid var(--border-subtle);
  padding: 8px 12px;
  text-align: center;
  vertical-align: middle;
}

.mlv-ev-matrix tbody tr:hover {
  background: rgba(255, 255, 255, 0.015);
}

.mlv-ev-case-col {
  text-align: left !important;
  min-width: 140px;
}

.mlv-ev-case-name {
  display: block;
  color: var(--text-body);
  font-weight: 600;
  font-size: 0.76rem;
}

.mlv-ev-group-tag {
  display: inline-block;
  margin-top: 2px;
  color: var(--text-dim);
  font-size: 0.62rem;
}

.ev-check {
  color: var(--green);
  font-weight: 800;
  font-size: 0.85rem;
}

.ev-miss {
  color: var(--text-dim);
  font-size: 0.78rem;
}

.ev-unknown {
  color: var(--amber);
  font-weight: 700;
  font-size: 0.8rem;
}

/* ===== AI Gates ===== */
.mlv-gate-list {
  display: grid;
  gap: 8px;
  margin-top: 16px;
}

.mlv-gate-card {
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(31, 38, 50, 0.96), rgba(17, 21, 30, 0.96)),
    repeating-linear-gradient(90deg, rgba(255,255,255,0.035) 0 1px, transparent 1px 34px);
  overflow: hidden;
}

.mlv-gate-card.expanded {
  border-color: var(--accent-border);
}

.mlv-gate-summary {
  display: grid;
  grid-template-columns: auto 1fr auto;
  grid-template-rows: auto auto;
  gap: 4px 12px;
  width: 100%;
  border: none;
  padding: 14px 16px;
  background: none;
  color: var(--text-body);
  text-align: left;
  cursor: pointer;
}

.mlv-gate-summary:hover {
  background: rgba(255, 255, 255, 0.015);
}

.mlv-gate-summary strong {
  grid-column: 1;
  grid-row: 1;
  color: var(--text-heading);
  font-size: 0.85rem;
}

.mlv-gate-summary p {
  grid-column: 2;
  grid-row: 1 / 3;
  margin: 0;
  color: var(--text-muted);
  font-size: 0.78rem;
  line-height: 1.55;
}

.mlv-gate-chevron {
  grid-column: 3;
  grid-row: 1 / 3;
  align-self: center;
  color: var(--text-dim);
  transition: transform var(--transition-fast);
}

.mlv-gate-chevron.open {
  transform: rotate(90deg);
}

.mlv-gate-detail {
  border-top: 1px solid var(--border-subtle);
  padding: 12px 16px 14px;
  background: var(--bg-input);
}

.mlv-gate-detail h4 {
  margin: 0 0 4px;
  color: var(--accent);
  font-size: 0.74rem;
  font-weight: 700;
}

.mlv-gate-detail p {
  margin: 0;
  color: var(--text-body);
  font-size: 0.8rem;
  line-height: 1.65;
}

/* ===== Roadmap ===== */
.mlv-roadmap-list {
  display: grid;
  gap: 10px;
  margin-top: 16px;
  counter-reset: roadmap;
}

.mlv-roadmap-item {
  display: flex;
  gap: 14px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 14px 16px;
  background:
    linear-gradient(180deg, rgba(31, 38, 50, 0.96), rgba(17, 21, 30, 0.96)),
    repeating-linear-gradient(90deg, rgba(255,255,255,0.035) 0 1px, transparent 1px 34px);
}

.mlv-roadmap-item.complete {
  border-left: 3px solid var(--green);
}

.mlv-roadmap-left {
  display: flex;
  align-items: flex-start;
  padding-top: 3px;
}

.mlv-roadmap-dot {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  flex-shrink: 0;
}

.mlv-roadmap-body {
  flex: 1;
  min-width: 0;
}

.mlv-roadmap-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.mlv-roadmap-name {
  color: var(--text-heading);
  font-size: 0.85rem;
  font-weight: 700;
}

.mlv-roadmap-group {
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  padding: 1px 8px;
  color: var(--text-dim);
  font-size: 0.62rem;
  font-weight: 600;
}

.mlv-roadmap-status {
  margin-left: auto;
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 0.65rem;
  font-weight: 700;
}

.st-ready {
  border: 1px solid rgba(46, 204, 113, 0.3);
  background: rgba(46, 204, 113, 0.1);
  color: var(--green);
}

.st-wip {
  border: 1px solid rgba(245, 166, 35, 0.25);
  background: rgba(245, 166, 35, 0.08);
  color: var(--amber);
}

.mlv-roadmap-steps {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.mlv-roadmap-step {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--text-muted);
  font-size: 0.74rem;
}

.mlv-roadmap-step.done {
  color: var(--green);
}

.mlv-step-icon {
  font-size: 0.7rem;
  font-weight: 800;
}

.mlv-roadmap-arrow {
  color: var(--text-dim);
  font-size: 0.7rem;
}

.mlv-roadmap-next {
  display: block;
  margin-top: 6px;
  color: var(--text-dim);
  font-size: 0.7rem;
  font-style: italic;
}

/* ===== Responsive ===== */
@media (max-width: 820px) {
  .mlv-body {
    display: block;
  }

  .mlv-sidebar {
    display: flex;
    width: auto;
    border-right: 0;
    border-bottom: 1px solid var(--border-subtle);
    overflow-x: auto;
  }

  .mlv-sidebar-head {
    display: none;
  }

  .mlv-file-btn {
    min-width: 160px;
  }

  .mlv-stats-row {
    grid-template-columns: repeat(2, 1fr);
  }

  .mlv-ev-legend {
    display: flex;
    flex-wrap: wrap;
    margin-left: 0;
    margin-top: 6px;
  }
}
</style>
