<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { listen } from '@tauri-apps/api/event';
import { invoke } from '@tauri-apps/api/core';

const DOMAIN = 'localhost';
const PORT = '8008';

type CleanupFunction = () => void;

interface ConnectionStatus {
  connected: boolean;
  host: string;
  pid: string;
  message: string;
}

interface RemoteStatus {
  checked: boolean;
  connected: boolean;
  running: boolean;
  runId: string;
  message: string;
  output: string;
}

interface SolverTile {
  name: string;
  domain: string;
  status: 'planned' | 'waiting';
  note: string;
}

interface RunRecord {
  caseName: string;
  solver: string;
  status: string;
  detail: string;
}

const status = ref<ConnectionStatus>({
  connected: false,
  host: '',
  pid: '',
  message: '尚未验证侧车服务连接。',
});

const remoteStatus = ref<RemoteStatus>({
  checked: false,
  connected: false,
  running: false,
  runId: '',
  message: '尚未测试远程计算节点。',
  output: '',
});

const logs = ref('[界面] 正在监听侧车服务和网络日志...');
let cleanupListeners: CleanupFunction | null = null;
let remoteEventSource: EventSource | null = null;

const solvers: SolverTile[] = [
  {
    name: 'CalculiX',
    domain: '结构有限元',
    status: 'waiting',
    note: '优先用于小型、可检查、适合学习拆解的有限元案例。',
  },
  {
    name: 'OpenFOAM',
    domain: '流体动力学',
    status: 'planned',
    note: '预留给后续命令行镜像接入和运行日志采集。',
  },
  {
    name: 'Elmer',
    domain: '多物理场',
    status: 'planned',
    note: '基础外壳稳定后，用于耦合物理实验的入口。',
  },
];

const runRecords = computed<RunRecord[]>(() => [
  {
    caseName: '概念验证链路',
    solver: 'FastAPI 侧车服务',
    status: status.value.connected ? '已验证' : '待验证',
    detail: status.value.connected
      ? `已连接到 ${status.value.host}，进程号 ${status.value.pid}。`
      : '点击连接验证，确认 Vue 可以调用 Python 侧车服务。',
  },
  {
    caseName: '远程计算节点',
    solver: 'SSH 通道 shh1',
    status: remoteStatus.value.connected ? '已连通' : '待测试',
    detail: remoteStatus.value.connected
      ? '侧车服务已经能通过 SSH 调用远程节点并取回输出。'
      : '先测试 SSH 通道，后续再接求解器和实时日志流。',
  },
  {
    caseName: '求解器镜像桥接',
    solver: 'CalculiX / OpenFOAM / Elmer',
    status: '下一阶段',
    detail: '镜像和求解器执行暂不接入，留给下一阶段实现。',
  },
]);

const connectionLabel = computed(() =>
  status.value.connected ? '侧车服务在线' : '侧车服务待验证',
);

const remoteLabel = computed(() =>
  remoteStatus.value.connected ? '远程节点在线' : '远程节点待测试',
);

const appendLog = (line: string) => {
  logs.value += `\n${line}`;
};

const initSidecarListeners = async () => {
  const unlistenStdout = await listen<string>('sidecar-stdout', (event) => {
    if (event.payload?.length > 0 && event.payload !== '\r\n') {
      appendLog(event.payload);
    }
  });

  const unlistenStderr = await listen<string>('sidecar-stderr', (event) => {
    if (event.payload?.length > 0 && event.payload !== '\r\n') {
      appendLog(event.payload);
    }
  });

  cleanupListeners = () => {
    unlistenStdout();
    unlistenStderr();
  };
};

const apiAction = async (endpoint: string, method: string = 'GET'): Promise<any> => {
  const url = `http://${DOMAIN}:${PORT}/${endpoint}`;
  try {
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
    });

    if (!res.ok) {
      throw new Error(`响应状态：${res.status} ${await res.text()}`);
    }

    const json = await res.json();
    if (json?.message) {
      appendLog(`[服务响应] ${json.message}`);
    }
    return json;
  } catch (err: any) {
    appendLog(`[服务响应] ${err}`);
    throw err;
  }
};

const connectServerAction = async () => {
  try {
    const result = await apiAction('v1/connect');
    status.value = {
      connected: true,
      host: result.data.host,
      pid: String(result.data.pid),
      message: '侧车服务连接成功。',
    };
  } catch (err) {
    status.value = {
      connected: false,
      host: '',
      pid: '',
      message: '连接失败，请确认侧车服务已启动。',
    };
    appendLog(`[界面] 连接 API 服务失败：${err}`);
  }
};

const probeRemoteNodeAction = async () => {
  try {
    remoteStatus.value = {
      checked: true,
      connected: false,
      running: false,
      runId: '',
      message: '正在测试 shh1 远程节点...',
      output: '',
    };
    const result = await apiAction('v1/compute-nodes/shh1/probe');
    const details = result.data.details ?? {};
    const output = [
      `主机：${details.hostname ?? '未知'}`,
      `用户：${details.user ?? '未知'}`,
      `CPU 核心：${details.cpu_cores ?? '未知'}`,
      `当前目录：${details.workdir ?? '未知'}`,
      `耗时：${result.data.duration_seconds} 秒`,
    ].join('\n');
    remoteStatus.value = {
      checked: true,
      connected: result.data.connected,
      running: false,
      runId: '',
      message: result.data.connected ? 'shh1 远程节点连接成功。' : 'shh1 远程节点连接失败。',
      output: `${output}${result.data.stderr ? `\n错误输出：\n${result.data.stderr}` : ''}`.trim(),
    };
  } catch (err) {
    remoteStatus.value = {
      checked: true,
      connected: false,
      running: false,
      runId: '',
      message: 'shh1 远程节点测试失败。',
      output: String(err),
    };
  }
};

const startRemoteDemoRunAction = async () => {
  try {
    remoteEventSource?.close();
    remoteStatus.value = {
      ...remoteStatus.value,
      checked: true,
      running: true,
      message: '正在启动远程终端测试任务...',
      output: '',
    };

    const result = await apiAction('v1/runs/shh1/demo', 'POST');
    const runId = result.data.run_id;
    remoteStatus.value = {
      ...remoteStatus.value,
      runId,
      message: `远程任务 ${runId} 已启动，正在接收实时输出。`,
    };

    remoteEventSource = new EventSource(`http://${DOMAIN}:${PORT}/v1/runs/${runId}/events`);
    remoteEventSource.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.line) {
        remoteStatus.value.output += `${payload.line}\n`;
        appendLog(`[远程任务] ${payload.line}`);
      }
      if (payload.type === 'finished') {
        remoteStatus.value = {
          ...remoteStatus.value,
          connected: payload.exit_code === 0,
          running: false,
          message: payload.exit_code === 0 ? '远程测试任务已完成。' : '远程测试任务失败。',
        };
        remoteEventSource?.close();
        remoteEventSource = null;
      }
    };
    remoteEventSource.onerror = () => {
      remoteStatus.value = {
        ...remoteStatus.value,
        running: false,
        message: '远程实时日志通道中断。',
      };
      remoteEventSource?.close();
      remoteEventSource = null;
    };
  } catch (err) {
    remoteStatus.value = {
      ...remoteStatus.value,
      running: false,
      message: '远程测试任务启动失败。',
      output: String(err),
    };
  }
};

const shutdownSidecarAction = async () => {
  try {
    await invoke('shutdown_sidecar');
    status.value = {
      connected: false,
      host: '',
      pid: '',
      message: '已请求停止侧车服务。',
    };
    appendLog('[界面] 已请求停止侧车服务。');
  } catch (err) {
    appendLog(`[界面] 停止侧车服务失败：${err}`);
  }
};

const startSidecarAction = async () => {
  try {
    await invoke('start_sidecar');
    appendLog('[界面] 已请求启动侧车服务，正在尝试连接...');
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
  cleanupListeners?.();
  remoteEventSource?.close();
  window.removeEventListener('keydown', handleKeydown);
});
</script>

<template>
  <main class="studio-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">SimFEA Studio 概念验证</p>
        <h1>仿真学习的桌面外壳</h1>
        <p class="mission">
          包装开源命令行求解器，记录每一次亲手拆解过的物理概念。
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

    <section class="workspace-grid" aria-label="项目仪表盘">
      <section class="panel project-panel" aria-labelledby="project-title">
        <div class="section-heading">
          <p class="eyebrow">当前项目</p>
          <h2 id="project-title">概念验证链路</h2>
        </div>
        <p class="body-copy">
          当前阶段验证 Tauri、Vue、FastAPI 侧车服务、SSH 远程计算节点的通信链路。镜像、求解器执行、VTK
          结果视图都留到下一阶段接入。
        </p>
        <dl class="facts">
          <div>
            <dt>前端</dt>
            <dd>Vue / Vite，地址 localhost:3000</dd>
          </div>
          <div>
            <dt>后端</dt>
            <dd>FastAPI 侧车服务，地址 localhost:8008</dd>
          </div>
          <div>
            <dt>远程节点</dt>
            <dd>SSH 通道 shh1</dd>
          </div>
        </dl>
      </section>

      <section class="panel control-panel" aria-labelledby="control-title">
        <div class="section-heading">
          <p class="eyebrow">概念验证控制台</p>
          <h2 id="control-title">侧车服务验证</h2>
        </div>
        <div class="button-row">
          <button class="primary-action" type="button" @click="connectServerAction">
            验证连接
          </button>
          <button type="button" @click="startSidecarAction" :disabled="status.connected">
            启动侧车服务
          </button>
          <button type="button" @click="shutdownSidecarAction" :disabled="!status.connected">
            停止侧车服务
          </button>
        </div>
        <div class="connection-detail">
          <span>{{ status.message }}</span>
          <span v-if="status.connected">服务地址：{{ status.host }}</span>
          <span v-if="status.connected">进程号：{{ status.pid }}</span>
        </div>
      </section>

      <section class="panel remote-panel" aria-labelledby="remote-title">
        <div class="section-heading">
          <p class="eyebrow">远程算力</p>
          <h2 id="remote-title">SSH 通道 shh1</h2>
        </div>
        <p class="body-copy">
          这是第一个远程计算节点入口。当前只执行探测命令，证明侧车服务能通过 SSH 获取远程输出。
        </p>
        <div class="button-row">
          <button type="button" class="primary-action" @click="probeRemoteNodeAction" :disabled="!status.connected">
            测试远程节点
          </button>
          <button type="button" @click="startRemoteDemoRunAction" :disabled="!status.connected || remoteStatus.running">
            运行远程测试任务
          </button>
        </div>
        <div class="connection-detail">
          <span>{{ remoteStatus.message }}</span>
        </div>
        <pre v-if="remoteStatus.output" class="remote-output"><code>{{ remoteStatus.output }}</code></pre>
      </section>

      <section class="panel solver-panel" aria-labelledby="solver-title">
        <div class="section-heading">
          <p class="eyebrow">求解器桥接</p>
          <h2 id="solver-title">求解器入口占位</h2>
        </div>
        <div class="solver-list">
          <article v-for="solver in solvers" :key="solver.name" class="solver-tile">
            <div>
              <h3>{{ solver.name }}</h3>
              <p>{{ solver.domain }}</p>
            </div>
            <span class="tile-status">{{ solver.status === 'waiting' ? '下一步' : '已规划' }}</span>
            <p class="tile-note">{{ solver.note }}</p>
          </article>
        </div>
      </section>

      <section class="panel runs-panel" aria-labelledby="runs-title">
        <div class="section-heading">
          <p class="eyebrow">物证仓库</p>
          <h2 id="runs-title">运行记录</h2>
        </div>
        <div class="run-table" role="table" aria-label="运行记录">
          <div class="run-row run-head" role="row">
            <span role="columnheader">案例</span>
            <span role="columnheader">求解器</span>
            <span role="columnheader">状态</span>
          </div>
          <div v-for="run in runRecords" :key="run.caseName" class="run-row" role="row">
            <span role="cell">{{ run.caseName }}</span>
            <span role="cell">{{ run.solver }}</span>
            <span role="cell">{{ run.status }}</span>
            <p>{{ run.detail }}</p>
          </div>
        </div>
      </section>

      <section class="panel log-panel" aria-labelledby="log-title">
        <div class="section-heading compact-heading">
          <p class="eyebrow">运行日志</p>
          <h2 id="log-title">侧车服务日志</h2>
        </div>
        <pre class="logs-display"><code>{{ logs }}</code></pre>
      </section>
    </section>
  </main>
</template>
