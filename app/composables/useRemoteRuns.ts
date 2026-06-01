import { computed, ref } from 'vue'
import type { SimfeaClient } from '@/api/simfeaClient'
import type { RunEventHandlers } from '@/composables/useRunEvents'
import type { SolverDefinition } from '@/types'

export interface ComputeNodeConfig {
  alias: string
  label: string
  host: string
  user: string
  port?: number
  remote_runs_root: string
  configured: boolean
}

export interface RemoteStatus {
  checked: boolean
  connected: boolean
  running: boolean
  runId: string
  message: string
  output: string
  archivePath: string
  remoteWorkdir: string
}

export interface UseRemoteRunsOptions {
  api: SimfeaClient
  openRunEventStream: (runId: string, handlers: RunEventHandlers) => void
  closeRunEventStream: () => void
  onRunFinished: (runId: string) => Promise<void>
  appendLog: (line: string) => void
}

export function useRemoteRuns(options: UseRemoteRunsOptions) {
  const { api, openRunEventStream, closeRunEventStream, onRunFinished, appendLog } = options

  const remoteStatus = ref<RemoteStatus>({
    checked: false,
    connected: false,
    running: false,
    runId: '',
    message: '尚未测试远程计算节点。',
    output: '',
    archivePath: '',
    remoteWorkdir: '',
  })

  const computeNodes = ref<ComputeNodeConfig[]>([])
  const selectedComputeNode = ref('')
  const solvers = ref<SolverDefinition[]>([])

  const activeComputeNode = computed(
    () => computeNodes.value.find((node) => node.alias === selectedComputeNode.value) ?? null
  )

  const activeComputeNodeLabel = computed(
    () => activeComputeNode.value?.label || selectedComputeNode.value || '未配置计算节点'
  )

  const remoteLabel = computed(() => (remoteStatus.value.connected ? '远程节点在线' : '远程节点待测试'))

  const setComputeNodes = (nodes: ComputeNodeConfig[], defaultNode: string) => {
    computeNodes.value = nodes
    selectedComputeNode.value = defaultNode || nodes[0]?.alias || ''
  }

  const setSolvers = (items: SolverDefinition[]) => {
    solvers.value = items
  }

  const probeRemoteNodeAction = async () => {
    if (!selectedComputeNode.value) {
      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        connected: false,
        running: false,
        message: '请先在配置文件中添加计算节点。',
        output: '',
      }
      return
    }

    const label = activeComputeNodeLabel.value
    try {
      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        connected: false,
        running: false,
        message: `正在测试 ${label}...`,
        output: '',
      }
      const result = await api.probeComputeNode(selectedComputeNode.value)
      const details = result.data.details ?? {}
      const output = [
        `主机：${details.hostname ?? '未知'}`,
        `用户：${details.user ?? '未知'}`,
        `CPU 核心：${details.cpu_cores ?? '未知'}`,
        `远程目录：${details.workdir ?? '未知'}`,
        `探测耗时：${result.data.duration_seconds} 秒`,
      ].join('\n')

      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        connected: result.data.connected,
        running: false,
        message: result.data.connected ? `${label} 连接成功。` : `${label} 连接失败。`,
        output: `${output}${result.data.stderr ? `\n错误输出：\n${result.data.stderr}` : ''}`.trim(),
      }
    } catch (err) {
      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        connected: false,
        running: false,
        message: `${label} 测试失败。`,
        output: String(err),
      }
    }
  }

  const probeSchedulerAction = async () => {
    if (!selectedComputeNode.value) {
      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        connected: false,
        running: false,
        message: '请先在配置文件中添加计算节点。',
        output: '',
      }
      return
    }

    const label = activeComputeNodeLabel.value
    try {
      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        message: `正在探测 ${label} 的作业调度器...`,
        output: '',
      }
      const result = await api.probeScheduler(selectedComputeNode.value)
      const details = result.data.details ?? {}
      const output = [
        `主机：${details.hostname ?? '未知'}`,
        `用户：${details.user ?? '未知'}`,
        `调度器：${details.scheduler ?? '未知'}`,
        `sbatch：${details.sbatch || '未发现'}`,
        `srun：${details.srun || '未发现'}`,
        `squeue：${details.squeue || '未发现'}`,
        `qsub：${details.qsub || '未发现'}`,
        `bsub：${details.bsub || '未发现'}`,
        `CPU 核心：${details.cpu_cores ?? '未知'}`,
        `内存：${details.memory ?? '未知'}`,
        `远程目录：${details.workdir ?? '未知'}`,
        `探测耗时：${result.data.duration_seconds} 秒`,
      ].join('\n')

      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        connected: result.data.connected,
        message: result.data.connected ? `${label} 调度器探测完成。` : `${label} 调度器探测失败。`,
        output: `${output}${result.data.stderr ? `\n错误输出：\n${result.data.stderr}` : ''}`.trim(),
      }
    } catch (err) {
      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        message: `${label} 调度器探测失败。`,
        output: String(err),
      }
    }
  }

  const probeSolversAction = async () => {
    if (!selectedComputeNode.value) {
      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        connected: false,
        running: false,
        message: '请先在配置文件中添加计算节点。',
        output: '',
      }
      return
    }

    const label = activeComputeNodeLabel.value
    try {
      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        message: `正在探测 ${label} 上的求解器...`,
        output: '',
      }
      const result = await api.probeSolvers(selectedComputeNode.value)
      const output = result.data.solvers
        .map((solver) => `${solver.label} / ${solver.alias}: ${solver.available ? solver.path : '未发现'}`)
        .join('\n')
      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        connected: result.data.connected,
        message: result.data.connected ? `${label} 求解器探测完成。` : `${label} 求解器探测失败。`,
        output: `${output}${result.data.stderr ? `\n错误输出：\n${result.data.stderr}` : ''}`.trim(),
      }
    } catch (err) {
      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        message: `${label} 求解器探测失败。`,
        output: String(err),
      }
    }
  }

  const startRemoteDemoRunAction = async () => {
    if (!selectedComputeNode.value) {
      remoteStatus.value = {
        ...remoteStatus.value,
        running: false,
        message: '请先在配置文件中添加计算节点。',
        output: '',
      }
      return
    }

    const label = activeComputeNodeLabel.value
    try {
      closeRunEventStream()
      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        running: true,
        message: '正在启动远程闭环样例...',
        output: '',
        archivePath: '',
        remoteWorkdir: '',
      }

      const result = await api.startDemoRun(selectedComputeNode.value)
      const runId = result.data.run_id
      remoteStatus.value = {
        ...remoteStatus.value,
        runId,
        archivePath: result.data.archive_path,
        remoteWorkdir: result.data.remote_workdir,
        message: `${label} 上的任务 ${runId} 已创建，正在接收实时日志。`,
      }

      openRunEventStream(runId, {
        onEvent: async (payload) => {
          if (payload.line) {
            remoteStatus.value.output += `${payload.line}\n`
            appendLog(`[远程任务] ${payload.line}`)
          }
          if (payload.archive_path) {
            remoteStatus.value.archivePath = payload.archive_path
          }
          if (payload.remote_workdir) {
            remoteStatus.value.remoteWorkdir = payload.remote_workdir
          }
          if (payload.type === 'finished') {
            const finishedNormally = payload.status === 'finished' && payload.exit_code === 0
            const canceled = payload.status === 'canceled'
            remoteStatus.value = {
              ...remoteStatus.value,
              connected: canceled ? remoteStatus.value.connected : finishedNormally,
              running: false,
              message: canceled
                ? '远程任务已取消，取消记录已进入物证仓库。'
                : finishedNormally
                  ? '远程闭环样例完成，日志和结果已进入物证仓库。'
                  : '远程闭环样例失败，请查看日志。',
            }
            closeRunEventStream()
            await onRunFinished(runId)
          }
        },
        onError: () => {
          remoteStatus.value = {
            ...remoteStatus.value,
            running: false,
            message: '远程实时日志通道中断。',
          }
          closeRunEventStream()
        },
      })
    } catch (err) {
      remoteStatus.value = {
        ...remoteStatus.value,
        running: false,
        message: '远程闭环样例启动失败。',
        output: String(err),
      }
    }
  }

  const startSlurmDemoRunAction = async () => {
    if (!selectedComputeNode.value) {
      remoteStatus.value = {
        ...remoteStatus.value,
        running: false,
        message: '请先在配置文件中添加计算节点。',
        output: '',
      }
      return
    }

    const label = activeComputeNodeLabel.value
    try {
      closeRunEventStream()
      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        running: true,
        message: '正在提交 Slurm 远程闭环样例...',
        output: '',
        archivePath: '',
        remoteWorkdir: '',
      }

      const result = await api.startSlurmDemoRun(selectedComputeNode.value)
      const runId = result.data.run_id
      const resourceLines = [
        `调度器：${result.data.scheduler ?? 'slurm'}`,
        `分区：${result.data.partition ?? '未知'}`,
        `申请 CPU：${result.data.requested_cpus ?? '未知'}`,
        `申请内存：${result.data.requested_memory ?? '未知'}`,
      ].join('\n')

      remoteStatus.value = {
        ...remoteStatus.value,
        runId,
        archivePath: result.data.archive_path,
        remoteWorkdir: result.data.remote_workdir,
        message: `${label} 已创建 Slurm 运行 ${runId}，正在等待 JobID 和实时日志。`,
        output: `${resourceLines}\n`,
      }

      openRunEventStream(runId, {
        onEvent: async (payload) => {
          if (payload.line) {
            remoteStatus.value.output += `${payload.line}\n`
            appendLog(`[SlurmRunner] ${payload.line}`)
          }
          if (payload.archive_path) {
            remoteStatus.value.archivePath = payload.archive_path
          }
          if (payload.remote_workdir) {
            remoteStatus.value.remoteWorkdir = payload.remote_workdir
          }
          if (payload.job_id) {
            remoteStatus.value.output += `JobID：${payload.job_id}\n`
          }
          if (payload.allocated_node) {
            remoteStatus.value.output += `运行节点：${payload.allocated_node}\n`
          }
          if (payload.type === 'finished') {
            const finishedNormally = payload.status === 'finished' && payload.exit_code === 0
            const canceled = payload.status === 'canceled'
            remoteStatus.value = {
              ...remoteStatus.value,
              connected: canceled ? remoteStatus.value.connected : finishedNormally,
              running: false,
              message: canceled
                ? 'Slurm 任务已取消，取消记录已进入物证仓库。'
                : finishedNormally
                  ? 'Slurm 闭环样例完成，真实计算节点日志和结果已归档。'
                  : 'Slurm 闭环样例失败，请查看 stderr 和学习报告。',
            }
            closeRunEventStream()
            await onRunFinished(runId)
          }
        },
        onError: () => {
          remoteStatus.value = {
            ...remoteStatus.value,
            running: false,
            message: 'Slurm 实时事件流中断。',
          }
          closeRunEventStream()
        },
      })
    } catch (err) {
      remoteStatus.value = {
        ...remoteStatus.value,
        running: false,
        message: 'Slurm 闭环样例提交失败。',
        output: String(err),
      }
    }
  }

  const startSolverRunAction = async (solverAlias: string) => {
    if (!selectedComputeNode.value) {
      remoteStatus.value = {
        ...remoteStatus.value,
        running: false,
        message: '请先在配置文件中添加计算节点。',
        output: '',
      }
      return
    }

    const solver = solvers.value.find((item) => item.alias === solverAlias)
    const label = activeComputeNodeLabel.value
    try {
      closeRunEventStream()
      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        running: true,
        message: `正在启动 ${solver?.label ?? solverAlias} 求解器运行...`,
        output: '',
        archivePath: '',
        remoteWorkdir: '',
      }

      const result = await api.startSolverRun(selectedComputeNode.value, solverAlias)
      const runId = result.data.run_id
      remoteStatus.value = {
        ...remoteStatus.value,
        runId,
        archivePath: result.data.archive_path,
        remoteWorkdir: result.data.remote_workdir,
        message: `${label} 上的 ${result.data.solver.label} 运行 ${runId} 已创建，正在接收实时日志。`,
      }

      openRunEventStream(runId, {
        onEvent: async (payload) => {
          if (payload.line) {
            remoteStatus.value.output += `${payload.line}\n`
            appendLog(`[SolverRunner] ${payload.line}`)
          }
          if (payload.archive_path) {
            remoteStatus.value.archivePath = payload.archive_path
          }
          if (payload.remote_workdir) {
            remoteStatus.value.remoteWorkdir = payload.remote_workdir
          }
          if (payload.type === 'finished') {
            const finishedNormally = payload.status === 'finished' && payload.exit_code === 0
            const canceled = payload.status === 'canceled'
            remoteStatus.value = {
              ...remoteStatus.value,
              connected: canceled ? remoteStatus.value.connected : finishedNormally,
              running: false,
              message: canceled
                ? '求解器任务已取消，取消记录已进入物证仓库。'
                : finishedNormally
                  ? '求解器运行完成，输入、日志和结果已进入物证仓库。'
                  : '求解器运行失败，请查看 stderr 和学习报告。',
            }
            closeRunEventStream()
            await onRunFinished(runId)
          }
        },
        onError: () => {
          remoteStatus.value = {
            ...remoteStatus.value,
            running: false,
            message: '求解器实时事件流中断。',
          }
          closeRunEventStream()
        },
      })
    } catch (err) {
      remoteStatus.value = {
        ...remoteStatus.value,
        running: false,
        message: '求解器运行启动失败。',
        output: String(err),
      }
    }
  }

  const startFreecadPrepomaxWorkflowAction = async () => {
    if (!selectedComputeNode.value) {
      remoteStatus.value = {
        ...remoteStatus.value,
        running: false,
        message: '请先选择一个计算节点。',
        output: '',
      }
      return
    }

    const label = activeComputeNodeLabel.value
    try {
      closeRunEventStream()
      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        running: true,
        message: '正在启动 FreeCAD -> PrePoMax 工作流...',
        output: '',
        archivePath: '',
        remoteWorkdir: '',
      }

      const result = await api.startFreecadPrepomaxWorkflow(selectedComputeNode.value)
      const runId = result.data.run_id
      remoteStatus.value = {
        ...remoteStatus.value,
        runId,
        archivePath: result.data.archive_path,
        remoteWorkdir: result.data.remote_workdir,
        message: `${label} 上的 ${result.data.workflow.label} 工作流 ${runId} 已创建，正在接收实时日志。`,
      }

      openRunEventStream(runId, {
        onEvent: async (payload) => {
          if (payload.line) {
            remoteStatus.value.output += `${payload.line}\n`
            appendLog(`[WorkflowRunner] ${payload.line}`)
          }
          if (payload.archive_path) {
            remoteStatus.value.archivePath = payload.archive_path
          }
          if (payload.remote_workdir) {
            remoteStatus.value.remoteWorkdir = payload.remote_workdir
          }
          if (payload.type === 'finished') {
            const finishedNormally = payload.status === 'finished' && payload.exit_code === 0
            const canceled = payload.status === 'canceled'
            remoteStatus.value = {
              ...remoteStatus.value,
              connected: canceled ? remoteStatus.value.connected : finishedNormally,
              running: false,
              message: canceled
                ? 'FreeCAD -> PrePoMax 工作流已取消。'
                : finishedNormally
                  ? 'FreeCAD -> PrePoMax 工作流完成，几何、前处理输出和日志已进入物证仓库。'
                  : 'FreeCAD -> PrePoMax 工作流失败，请查看 stderr 和归档日志。',
            }
            closeRunEventStream()
            await onRunFinished(runId)
          }
        },
        onError: () => {
          remoteStatus.value = {
            ...remoteStatus.value,
            running: false,
            message: 'FreeCAD -> PrePoMax 工作流事件流中断。',
          }
          closeRunEventStream()
        },
      })
    } catch (err) {
      remoteStatus.value = {
        ...remoteStatus.value,
        running: false,
        message: 'FreeCAD -> PrePoMax 工作流启动失败。',
        output: String(err),
      }
    }
  }

  const startCustomWorkflowAction = async (steps: string[]) => {
    if (!selectedComputeNode.value) {
      remoteStatus.value = {
        ...remoteStatus.value,
        running: false,
        message: '请先选择一个计算节点。',
        output: '',
      }
      return
    }

    const label = activeComputeNodeLabel.value
    try {
      closeRunEventStream()
      remoteStatus.value = {
        ...remoteStatus.value,
        checked: true,
        running: true,
        message: `正在启动自定义工作流 (${steps.length} 步)...`,
        output: '',
        archivePath: '',
        remoteWorkdir: '',
      }

      const result = await api.startCustomWorkflow(selectedComputeNode.value, steps)
      const runId = result.data.run_id
      const skippedInfo = result.data.skipped_steps?.length
        ? ` (跳过 ${result.data.skipped_steps.length} 个无配置步骤)`
        : ''
      remoteStatus.value = {
        ...remoteStatus.value,
        runId,
        archivePath: result.data.archive_path,
        remoteWorkdir: result.data.remote_workdir,
        message: `${label} 上的 ${result.data.workflow.label} 工作流 ${runId} 已创建${skippedInfo}，正在接收实时日志。`,
      }

      openRunEventStream(runId, {
        onEvent: async (payload) => {
          if (payload.line) {
            remoteStatus.value.output += `${payload.line}\n`
            appendLog(`[WorkflowRunner] ${payload.line}`)
          }
          if (payload.archive_path) {
            remoteStatus.value.archivePath = payload.archive_path
          }
          if (payload.remote_workdir) {
            remoteStatus.value.remoteWorkdir = payload.remote_workdir
          }
          if (payload.type === 'finished') {
            const finishedNormally = payload.status === 'finished' && payload.exit_code === 0
            const canceled = payload.status === 'canceled'
            remoteStatus.value = {
              ...remoteStatus.value,
              connected: canceled ? remoteStatus.value.connected : finishedNormally,
              running: false,
              message: canceled
                ? '自定义工作流已取消。'
                : finishedNormally
                  ? '自定义工作流完成，输入、日志和结果已进入物证仓库。'
                  : '自定义工作流失败，请查看 stderr 和归档日志。',
            }
            closeRunEventStream()
            await onRunFinished(runId)
          }
        },
        onError: () => {
          remoteStatus.value = {
            ...remoteStatus.value,
            running: false,
            message: '自定义工作流事件流中断。',
          }
          closeRunEventStream()
        },
      })
    } catch (err) {
      remoteStatus.value = {
        ...remoteStatus.value,
        running: false,
        message: '自定义工作流启动失败。',
        output: String(err),
      }
    }
  }

  const cancelRemoteRunAction = async () => {
    if (!remoteStatus.value.runId) {
      remoteStatus.value = {
        ...remoteStatus.value,
        message: '当前没有可取消的运行任务。',
      }
      return
    }

    try {
      await api.cancelRun(remoteStatus.value.runId)
      remoteStatus.value = {
        ...remoteStatus.value,
        running: true,
        message: `已请求取消任务 ${remoteStatus.value.runId}，等待远程通道结束。`,
      }
    } catch (err) {
      remoteStatus.value = {
        ...remoteStatus.value,
        message: `取消任务失败：${err}`,
      }
    }
  }

  const clearRemoteOutputAction = () => {
    remoteStatus.value = {
      ...remoteStatus.value,
      output: '',
      message: '已清空远程输出。',
    }
  }

  return {
    remoteStatus,
    computeNodes,
    solvers,
    selectedComputeNode,
    activeComputeNode,
    activeComputeNodeLabel,
    remoteLabel,
    setComputeNodes,
    setSolvers,
    probeRemoteNodeAction,
    probeSchedulerAction,
    probeSolversAction,
    startRemoteDemoRunAction,
    startSlurmDemoRunAction,
    startSolverRunAction,
    startFreecadPrepomaxWorkflowAction,
    startCustomWorkflowAction,
    cancelRemoteRunAction,
    clearRemoteOutputAction,
  }
}
