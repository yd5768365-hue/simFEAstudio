import { contract, createClient } from '@/api/client'
import {
  cancelRunResponseSchema,
  connectResponseSchema,
  exportLearningBodySchema,
  exportLearningResponseSchema,
  generateReportResponseSchema,
  getRunResponseSchema,
  listRunsResponseSchema,
  probeNodeResponseSchema,
  probeSchedulerResponseSchema,
  saveNoteBodySchema,
  saveNoteResponseSchema,
  startDemoRunResponseSchema,
  startSlurmDemoRunResponseSchema,
} from '@/api/contracts'

const connectContract = contract({
  method: 'GET',
  path: '/v1/connect',
  response: connectResponseSchema,
})

const listRunsContract = contract({
  method: 'GET',
  path: '/v1/runs',
  response: listRunsResponseSchema,
})

const getRunContract = contract({
  method: 'GET',
  path: '/v1/runs/:runId',
  params: ['runId'] as const,
  response: getRunResponseSchema,
})

const saveNoteContract = contract({
  method: 'POST',
  path: '/v1/runs/:runId/note',
  params: ['runId'] as const,
  body: saveNoteBodySchema,
  response: saveNoteResponseSchema,
})

const generateReportContract = contract({
  method: 'GET',
  path: '/v1/runs/:runId/report',
  params: ['runId'] as const,
  response: generateReportResponseSchema,
})

const exportLearningContract = contract({
  method: 'POST',
  path: '/v1/runs/:runId/learning-export',
  params: ['runId'] as const,
  body: exportLearningBodySchema,
  response: exportLearningResponseSchema,
})

const probeNodeContract = contract({
  method: 'GET',
  path: '/v1/compute-nodes/:alias/probe',
  params: ['alias'] as const,
  response: probeNodeResponseSchema,
})

const probeSchedulerContract = contract({
  method: 'GET',
  path: '/v1/compute-nodes/:alias/scheduler-probe',
  params: ['alias'] as const,
  response: probeSchedulerResponseSchema,
})

const startDemoRunContract = contract({
  method: 'POST',
  path: '/v1/runs/:alias/demo',
  params: ['alias'] as const,
  response: startDemoRunResponseSchema,
})

const startSlurmDemoRunContract = contract({
  method: 'POST',
  path: '/v1/runs/:alias/slurm-demo',
  params: ['alias'] as const,
  response: startSlurmDemoRunResponseSchema,
})

const cancelRunContract = contract({
  method: 'POST',
  path: '/v1/runs/:runId/cancel',
  params: ['runId'] as const,
  response: cancelRunResponseSchema,
})

export function createSimfeaClient(baseUrl: string, appendLog: (line: string) => void) {
  const { request } = createClient(baseUrl, appendLog)

  return {
    connect: () => request(connectContract),
    listRuns: () => request(listRunsContract),
    getRun: (runId: string) => request(getRunContract, { params: { runId } }),
    saveRunNote: (runId: string, note: string) =>
      request(saveNoteContract, { params: { runId }, body: { note } }),
    generateRunReport: (runId: string) => request(generateReportContract, { params: { runId } }),
    exportLearningRecord: (runId: string, format: string, targetDir?: string) =>
      request(exportLearningContract, {
        params: { runId },
        body: { format, target_dir: targetDir || undefined },
      }),
    probeComputeNode: (alias: string) => request(probeNodeContract, { params: { alias } }),
    probeScheduler: (alias: string) => request(probeSchedulerContract, { params: { alias } }),
    startDemoRun: (alias: string) => request(startDemoRunContract, { params: { alias } }),
    startSlurmDemoRun: (alias: string) => request(startSlurmDemoRunContract, { params: { alias } }),
    cancelRun: (runId: string) => request(cancelRunContract, { params: { runId } }),
  }
}

export type SimfeaClient = ReturnType<typeof createSimfeaClient>
