<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { invoke } from '@tauri-apps/api/core';
import ResultEvidenceView from './components/ResultEvidenceView.vue';
import type { RunArchive, ToolchainItem } from './types';
import { createSimfeaClient } from './api/simfeaClient';
import { useSidecarListeners } from './composables/useSidecarListeners';
import { useRunEvents } from './composables/useRunEvents';
import { useRemoteRuns } from './composables/useRemoteRuns';

const configuredApiBaseUrl = import.meta.env.VITE_SIMFEA_API_BASE_URL as string | undefined;
const apiBaseUrl = (configuredApiBaseUrl?.replace(/\/$/, '') || `http://${window.location.hostname || 'localhost'}:8008`);

interface ConnectionStatus {
  connected: boolean;
  host: string;
  pid: string;
  runsRoot: string;
  configPath: string;
  learningExportRoot: string;
  learningFormats: string[];
  learningDefaultFormat: string;
  message: string;
}

interface ComputeNodeConfig {
  alias: string;
  label: string;
  host: string;
  user: string;
  port?: number;
  remote_runs_root: string;
  configured: boolean;
}

const status = ref<ConnectionStatus>({
  connected: false,
  host: '',
  pid: '',
  runsRoot: '',
  configPath: '',
  learningExportRoot: '',
  learningFormats: ['md', 'json', 'txt'],
  learningDefaultFormat: 'md',
  message: '尚未验证侧车服务连接。',
});

const computeNodes = ref<ComputeNodeConfig[]>([]);
const selectedComputeNode = ref('');
const archivedRuns = ref<RunArchive[]>([]);
const selectedRun = ref<RunArchive | null>(null);
const toolchainItems = ref<ToolchainItem[]>([]);
const learningNote = ref('');
const reportPreview = ref('');
const learningExportTarget = ref('');
const selectedLearningFormat = ref('md');
const noteMessage = ref('选择一次运行后，可以写下这次计算的判断、错误和下一步。');
const reportMessage = ref('运行完成后，这里会显示自动生成的学习沉淀报告。');
const exportMessage = ref('学习记录可以导出到配置目录，也可以临时指定一个目录。');
const logs = ref('[界面] 正在监听侧车服务和网络日志...');

const evidenceArtifacts = computed(() =>
  selectedRun.value?.artifacts?.filter((artifact) => artifact !== 'artifacts/result_summary.json') ?? [],
);

const selectedArtifacts = computed(() =>
  evidenceArtifacts.value.length ? evidenceArtifacts.value.join('、') : '暂无结果文件',
);

const selectedToolchain = computed<ToolchainItem[]>(() => selectedRun.value?.toolchain ?? toolchainItems.value);

const availableLearningFormats = computed(() =>
  status.value.learningFormats.length > 0 ? status.value.learningFormats : ['md', 'json', 'txt'],
);

const activeComputeNode = computed(() =>
  computeNodes.value.find((node) => node.alias === selectedComputeNode.value) ?? null,
);

const activeComputeNodeLabel = computed(() => activeComputeNode.value?.label || selectedComputeNode.value || '未配置计算节点');

const appendLog = (line: string) => {
  logs.value += `\n${line}`;
};

const api = createSimfeaClient(apiBaseUrl, appendLog);
const { initSidecarListeners, disposeSidecarListeners } = useSidecarListeners(appendLog);
const { openRunEventStream, closeRunEventStream } = useRunEvents(apiBaseUrl);

const remoteRuns = useRemoteRuns({
  api,
  openRunEventStream,
  closeRunEventStream,
  onRunFinished: async (runId: string) => {
    await loadRunsAction();
    await selectRunAction(runId);
  },
  appendLog,
});

const { remoteStatus } = remoteRuns;

const connectionLabel = computed(() =>
  status.value.connected ? '侧车服务在线' : '侧车服务待连接',
);

const remoteLabel = computed(() =>
  remoteStatus.value.connected ? '远程节点在线' : '远程节点待测试',
);

const loadRunsAction = async () => {
  const result = await api.listRuns();
  archivedRuns.value = result.data.runs ?? [];
  if (!selectedRun.value && archivedRuns.value.length > 0) {
    await selectRunAction(archivedRuns.value[0].run_id);
  }
};

const selectRunAction = async (runId: string) => {
  const result = await api.getRun(runId);
  if (!result.data) {
    noteMessage.value = '没有找到这次运行的归档。';
    return;
  }

  selectedRun.value = result.data;
  learningNote.value = result.data.note ?? '';
  reportPreview.value = result.data.report ?? '';
  noteMessage.value = `当前笔记：${result.data.local_archive}\\note.md`;
  reportMessage.value = result.data.learning_report
    ? `学习报告：${result.data.local_archive}\\${result.data.learning_report}`
    : '这次运行还没有生成学习报告。';
  exportMessage.value = result.data.learning_export
    ? `最近导出：${result.data.learning_export.path}`
    : '这次运行还没有导出到学习库。';
};

const saveNoteAction = async () => {
  if (!selectedRun.value) {
    noteMessage.value = '请先选择一次运行记录。';
    return;
  }

  const result = await api.saveRunNote(selectedRun.value.run_id, learningNote.value);
  noteMessage.value = result.data.saved
    ? `学习笔记已保存：${result.data.note_path}`
    : '学习笔记保存失败。';
  if (result.data.report_path) {
    reportMessage.value = `学习报告已刷新：${result.data.report_path}`;
  }
  await selectRunAction(selectedRun.value.run_id);
};

const refreshReportAction = async () => {
  if (!selectedRun.value) {
    reportMessage.value = '请先选择一次运行记录。';
    return;
  }

  const result = await api.generateRunReport(selectedRun.value.run_id);
  if (!result.data) {
    reportMessage.value = '学习报告生成失败。';
    return;
  }

  reportPreview.value = result.data.report;
  if (selectedRun.value && result.data.summary) {
    selectedRun.value = {
      ...selectedRun.value,
      summary: result.data.summary,
    };
  }
  reportMessage.value = `学习报告已生成：${result.data.report_path}`;
  await loadRunsAction();
};

const exportLearningRecordAction = async () => {
  if (!selectedRun.value) {
    exportMessage.value = '请先选择一次运行记录。';
    return;
  }

  const result = await api.exportLearningRecord(
    selectedRun.value.run_id,
    selectedLearningFormat.value,
    learningExportTarget.value.trim() || undefined,
  );
  if (!result.data?.exported) {
    exportMessage.value = '学习记录导出失败。';
    return;
  }

  exportMessage.value = `学习记录已导出：${result.data.export_path}`;
  if (result.data.summary) {
    selectedRun.value = {
      ...selectedRun.value,
      summary: result.data.summary,
      learning_export: result.data.record,
    };
  }
  await loadRunsAction();
};

const connectServerAction = async () => {
  try {
    const result = await api.connect();
    status.value = {
      connected: true,
      host: result.data.host,
      pid: String(result.data.pid),
      runsRoot: result.data.runs_root,
      configPath: result.data.config_path,
      learningExportRoot: result.data.learning_export_root,
      learningFormats: result.data.learning_formats ?? ['md', 'json', 'txt'],
      learningDefaultFormat: result.data.learning_default_format ?? 'md',
      message: '侧车服务连接成功。',
    };
    learningExportTarget.value = result.data.learning_export_root ?? '';
    selectedLearningFormat.value = result.data.learning_default_format ?? 'md';
    computeNodes.value = result.data.compute_nodes ?? [];
    selectedComputeNode.value = result.data.default_compute_node || computeNodes.value[0]?.alias || '';
    toolchainItems.value = result.data.toolchain ?? [];
    await loadRunsAction();
  } catch (err) {
    status.value = {
      connected: false,
      host: '',
      pid: '',
      runsRoot: '',
      configPath: '',
      learningExportRoot: '',
      learningFormats: ['md', 'json', 'txt'],
      learningDefaultFormat: 'md',
      message: '连接失败，请确认 FastAPI sidecar 已启动。',
    };
    appendLog(`[界面] 连接 API 服务失败：${err}`);
  }
};

const shutdownSidecarAction = async () => {
  try {
    await invoke('shutdown_sidecar');
    status.value = {
      connected: false,
      host: '',
      pid: '',
      runsRoot: '',
      configPath: '',
      learningExportRoot: '',
      learningFormats: ['md', 'json', 'txt'],
      learningDefaultFormat: 'md',
      message: '已请求关闭侧车服务。',
    };
    appendLog('[界面] 已请求关闭侧车服务。');
  } catch (err) {
    appendLog(`[界面] 关闭侧车服务失败：${err}`);
  }
};

const startSidecarAction = async () => {
  try {
    await invoke('start_sidecar');
    appendLog('[界面] 已请求启动侧车服务，稍后自动验证连接。');
    window.setTimeout(connectServerAction, 1000);
  } catch (err) {
    appendLog(`[界面] 启动侧车服务失败：${err}`);
  }
};

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'F11') {
    event.preventDefault();
    invoke('toggle_fullscreen');
  }
};

onMounted(() => {
  initSidecarListeners();
  window.addEventListener('keydown', handleKeydown);
});

onUnmounted(() => {
  disposeSidecarListeners();
  closeRunEventStream();
  window.removeEventListener('keydown', handleKeydown);
});
</script>

<template>
  <main class="studio-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">SimFEA Studio 物证工作台</p>
        <h1>远程运行、实时日志、结果归档、学习笔记</h1>
        <p class="mission">
          这个闭环先不追求完整求解器，而是把一次远程计算变成可回放的学习证据：
          命令、日志、结果文件、远程目录和个人复盘会被收进同一个运行档案。
        </p>
      </div>
      <div class="connection-stack">
        <div class="connection-pill" :class="{ online: status.connected }">
          <span class="status-dot" />
          <span>{{ connectionLabel }}</span>
        </div>
        <div class="connection-pill" :class="{ online: remoteStatus.connected }">
          <span class="status-dot" />
          <span>{{ remoteLabel }}</span>
        </div>
      </div>
    </header>

    <section class="workspace-grid" aria-label="SimFEA Studio 工作区">
      <section class="panel project-panel" aria-labelledby="project-title">
        <div class="section-heading">
          <p class="eyebrow">当前闭环</p>
          <h2 id="project-title">远程闭环样例</h2>
        </div>
        <p class="body-copy">
          任务会通过配置文件中的计算节点执行，在远程目录创建输入文件和结果文件，同时把 stdout/stderr 实时传回前端。
          结束后，侧车服务会把 result.txt 拉回本地 `.simfea/runs/` 归档目录。
        </p>
        <dl class="facts">
          <div>
            <dt>前端</dt>
            <dd>Vue / Vite</dd>
          </div>
          <div>
            <dt>侧车</dt>
            <dd>FastAPI / Python</dd>
          </div>
          <div>
            <dt>执行器</dt>
            <dd>SSHRunner / 配置节点</dd>
          </div>
        </dl>
      </section>

      <section class="panel control-panel" aria-labelledby="control-title">
        <div class="section-heading">
          <p class="eyebrow">侧车服务</p>
          <h2 id="control-title">本地控制面板</h2>
        </div>
        <div class="button-row">
          <button class="primary-action" type="button" @click="connectServerAction">
            验证连接
          </button>
          <button type="button" @click="startSidecarAction" :disabled="status.connected">
            启动侧车
          </button>
          <button type="button" @click="shutdownSidecarAction" :disabled="!status.connected">
            关闭侧车
          </button>
        </div>
        <div class="connection-detail">
          <span>{{ status.message }}</span>
          <span v-if="status.connected">API：{{ status.host }}</span>
          <span v-if="status.connected">进程：{{ status.pid }}</span>
          <span v-if="status.runsRoot">物证仓库：{{ status.runsRoot }}</span>
          <span v-if="status.learningExportRoot">学习库：{{ status.learningExportRoot }}</span>
          <span v-if="status.configPath">配置文件：{{ status.configPath }}</span>
        </div>
      </section>

      <section class="panel remote-panel" aria-labelledby="remote-title">
        <div class="section-heading">
          <p class="eyebrow">远程计算</p>
          <h2 id="remote-title">计算节点：{{ activeComputeNodeLabel }}</h2>
        </div>
        <label class="node-selector">
          <span>当前节点</span>
          <select v-model="selectedComputeNode" :disabled="computeNodes.length === 0 || remoteStatus.running">
            <option v-for="node in computeNodes" :key="node.alias" :value="node.alias">
              {{ node.label }} / {{ node.alias }}
            </option>
          </select>
        </label>
        <p v-if="computeNodes.length === 0" class="empty-state">
          尚未配置计算节点。请根据 simfea.config.example.json 创建 .simfea/config.json。
        </p>
        <div class="button-row">
          <button type="button" class="primary-action" @click="remoteRuns.probeRemoteNodeAction(selectedComputeNode, activeComputeNodeLabel)" :disabled="!status.connected || !selectedComputeNode">
            测试远程节点
          </button>
          <button type="button" @click="remoteRuns.probeSchedulerAction(selectedComputeNode, activeComputeNodeLabel)" :disabled="!status.connected || !selectedComputeNode || remoteStatus.running">
            探测调度器
          </button>
          <button type="button" @click="remoteRuns.startRemoteDemoRunAction(selectedComputeNode, activeComputeNodeLabel)" :disabled="!status.connected || !selectedComputeNode || remoteStatus.running">
            运行闭环样例
          </button>
          <button type="button" @click="remoteRuns.startSlurmDemoRunAction(selectedComputeNode, activeComputeNodeLabel)" :disabled="!status.connected || !selectedComputeNode || remoteStatus.running">
            运行 Slurm 样例
          </button>
          <button type="button" class="danger-action" @click="remoteRuns.cancelRemoteRunAction" :disabled="!remoteStatus.running || !remoteStatus.runId">
            取消当前任务
          </button>
        </div>
        <div class="connection-detail">
          <span>{{ remoteStatus.message }}</span>
          <span v-if="remoteStatus.remoteWorkdir">远程目录：{{ remoteStatus.remoteWorkdir }}</span>
          <span v-if="remoteStatus.archivePath">本地归档：{{ remoteStatus.archivePath }}</span>
        </div>
        <pre v-if="remoteStatus.output" class="remote-output"><code>{{ remoteStatus.output }}</code></pre>
      </section>

      <section class="panel toolchain-panel" aria-labelledby="toolchain-title">
        <div class="section-heading">
          <p class="eyebrow">工具链地图</p>
          <h2 id="toolchain-title">把竞品变成证据来源</h2>
        </div>
        <div class="toolchain-list">
          <article v-for="item in selectedToolchain" :key="item.name" class="toolchain-item">
            <div>
              <h3>{{ item.name }}</h3>
              <p>{{ item.role }}</p>
            </div>
            <span>{{ item.status }}</span>
          </article>
          <p v-if="selectedToolchain.length === 0" class="empty-state">
            工具链地图会从后端配置加载。
          </p>
        </div>
      </section>

      <section class="panel runs-panel" aria-labelledby="runs-title">
        <div class="section-heading">
          <p class="eyebrow">物证仓库</p>
          <h2 id="runs-title">运行记录</h2>
        </div>
        <div class="run-table" role="table" aria-label="运行记录">
          <div class="run-row run-head" role="row">
            <span role="columnheader">算例</span>
            <span role="columnheader">节点</span>
            <span role="columnheader">状态</span>
          </div>
          <button
            v-for="run in archivedRuns"
            :key="run.run_id"
            type="button"
            class="run-row run-button"
            :class="{ selected: selectedRun?.run_id === run.run_id }"
            @click="selectRunAction(run.run_id)"
          >
            <span>{{ run.case_name }}</span>
            <span>{{ run.compute_node }}</span>
            <span>{{ run.status }}</span>
            <p>{{ run.run_id }} / {{ run.local_archive }}</p>
          </button>
          <p v-if="archivedRuns.length === 0" class="empty-state">
            暂无运行记录。先点击“运行闭环样例”，生成第一份物证。
          </p>
        </div>
      </section>

      <ResultEvidenceView
        :run="selectedRun"
        :api-base-url="apiBaseUrl"
        :report-preview="reportPreview"
        :remote-output="remoteStatus.output"
      />

      <section class="panel note-panel" aria-labelledby="note-title">
        <div class="section-heading">
          <p class="eyebrow">学习笔记</p>
          <h2 id="note-title">本次复盘</h2>
        </div>
        <div v-if="selectedRun" class="run-summary">
          <span>运行：{{ selectedRun.run_id }}</span>
          <span>退出码：{{ selectedRun.exit_code ?? '未结束' }}</span>
          <span>结果：{{ selectedArtifacts }}</span>
        </div>
        <textarea
          v-model="learningNote"
          :disabled="!selectedRun"
          placeholder="例如：这次远程运行验证了什么？日志里有没有异常？结果文件说明了什么？下一步准备接哪个求解器？"
        />
        <div class="button-row">
          <button type="button" class="primary-action" @click="saveNoteAction" :disabled="!selectedRun">
            保存学习笔记
          </button>
        </div>
        <p class="note-message">{{ noteMessage }}</p>
      </section>

      <section class="panel export-panel" aria-labelledby="export-title">
        <div class="section-heading">
          <p class="eyebrow">长期沉淀</p>
          <h2 id="export-title">学习记录导出</h2>
        </div>
        <label class="field-label">
          <span>导出目录</span>
          <input
            v-model="learningExportTarget"
            :placeholder="status.learningExportRoot || '.simfea/learning'"
            :disabled="!selectedRun"
          />
        </label>
        <label class="field-label">
          <span>记录格式</span>
          <select v-model="selectedLearningFormat" :disabled="!selectedRun">
            <option v-for="format in availableLearningFormats" :key="format" :value="format">
              {{ format }}
            </option>
          </select>
        </label>
        <div class="button-row">
          <button type="button" class="primary-action" @click="exportLearningRecordAction" :disabled="!selectedRun">
            导出学习记录
          </button>
        </div>
        <p class="note-message">
          默认目录来自 .simfea/config.json；md 适合阅读，json 适合后续 AI agent 读取，txt 适合快速检索。
        </p>
        <p class="note-message">{{ exportMessage }}</p>
      </section>

      <section class="panel report-panel" aria-labelledby="report-title">
        <div class="section-heading">
          <p class="eyebrow">沉淀报告</p>
          <h2 id="report-title">learning_report.md</h2>
        </div>
        <div class="button-row">
          <button type="button" class="primary-action" @click="refreshReportAction" :disabled="!selectedRun">
            刷新学习报告
          </button>
        </div>
        <p class="note-message">{{ reportMessage }}</p>
        <pre v-if="reportPreview" class="report-preview"><code>{{ reportPreview }}</code></pre>
        <p v-else class="empty-state">
          选择一次运行记录后，这里会显示自动生成的学习沉淀报告。
        </p>
      </section>

      <section class="panel log-panel" aria-labelledby="log-title">
        <div class="section-heading compact-heading">
          <p class="eyebrow">实时日志</p>
          <h2 id="log-title">侧车与远程输出</h2>
        </div>
        <pre class="logs-display"><code>{{ logs }}</code></pre>
      </section>
    </section>
  </main>
</template>
