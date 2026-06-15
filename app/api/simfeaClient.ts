import { contract, createClient } from '@/api/client'
import {
  askKnowledgeBodySchema,
  askKnowledgeResponseSchema,
  cancelRunResponseSchema,
  connectResponseSchema,
  customWorkflowBodySchema,
  deleteKnowledgeResponseSchema,
  exportLearningBodySchema,
  exportLearningResponseSchema,
  generateReportResponseSchema,
  getBenchmarkCaseResponseSchema,
  getRunResponseSchema,
  guidedQuestionsResponseSchema,
  installSolverResponseSchema,
  listBenchmarksResponseSchema,
  listExperimentFilesResponseSchema,
  listKnowledgeResponseSchema,
  listRunsResponseSchema,
  listSolverInstallationsResponseSchema,
  listSolversResponseSchema,
  probeNodeResponseSchema,
  probeSchedulerResponseSchema,
  probeSolversResponseSchema,
  readExperimentFileResponseSchema,
  runExperimentCodeBodySchema,
  runExperimentCodeResponseSchema,
  saveExperimentFileBodySchema,
  saveExperimentFileResponseSchema,
  saveNoteBodySchema,
  saveNoteResponseSchema,
  solverExecutableBodySchema,
  solverInstallationResponseSchema,
  startCustomWorkflowRunResponseSchema,
  startDemoRunResponseSchema,
  startSlurmDemoRunResponseSchema,
  startSolverRunResponseSchema,
  startWorkflowRunResponseSchema,
  uploadKnowledgeResponseSchema,
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

const probeSolversContract = contract({
  method: 'GET',
  path: '/v1/compute-nodes/:alias/solvers/probe',
  params: ['alias'] as const,
  response: probeSolversResponseSchema,
})

const listSolversContract = contract({
  method: 'GET',
  path: '/v1/solvers',
  response: listSolversResponseSchema,
})

const listSolverInstallationsContract = contract({
  method: 'GET',
  path: '/v1/toolchain/solvers',
  response: listSolverInstallationsResponseSchema,
})

const scanSolverInstallationContract = contract({
  method: 'POST',
  path: '/v1/toolchain/solvers/:alias/scan',
  params: ['alias'] as const,
  response: solverInstallationResponseSchema,
})

const configureSolverExecutableContract = contract({
  method: 'POST',
  path: '/v1/toolchain/solvers/:alias/path',
  params: ['alias'] as const,
  body: solverExecutableBodySchema,
  response: solverInstallationResponseSchema,
})

const verifySolverInstallationContract = contract({
  method: 'POST',
  path: '/v1/toolchain/solvers/:alias/verify',
  params: ['alias'] as const,
  body: solverExecutableBodySchema,
  response: solverInstallationResponseSchema,
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

const startSolverRunContract = contract({
  method: 'POST',
  path: '/v1/runs/:alias/solvers/:solverAlias',
  params: ['alias', 'solverAlias'] as const,
  response: startSolverRunResponseSchema,
})

const startFreecadPrepomaxWorkflowContract = contract({
  method: 'POST',
  path: '/v1/runs/:alias/workflows/freecad-prepomax',
  params: ['alias'] as const,
  response: startWorkflowRunResponseSchema,
})

const startCustomWorkflowContract = contract({
  method: 'POST',
  path: '/v1/runs/:alias/workflows/custom',
  params: ['alias'] as const,
  body: customWorkflowBodySchema,
  response: startCustomWorkflowRunResponseSchema,
})

const cancelRunContract = contract({
  method: 'POST',
  path: '/v1/runs/:runId/cancel',
  params: ['runId'] as const,
  response: cancelRunResponseSchema,
})

const guidedQuestionsContract = contract({
  method: 'GET',
  path: '/v1/runs/:runId/guided-questions',
  params: ['runId'] as const,
  response: guidedQuestionsResponseSchema,
})

const installSolverContract = contract({
  method: 'POST',
  path: '/v1/toolchain/solvers/:alias/install',
  params: ['alias'] as const,
  response: installSolverResponseSchema,
})

const listKnowledgeDocumentsContract = contract({
  method: 'GET',
  path: '/v1/knowledge/documents',
  response: listKnowledgeResponseSchema,
})

const deleteKnowledgeDocumentContract = contract({
  method: 'DELETE',
  path: '/v1/knowledge/documents/:docId',
  params: ['docId'] as const,
  response: deleteKnowledgeResponseSchema,
})

const askKnowledgeContract = contract({
  method: 'POST',
  path: '/v1/knowledge/ask',
  body: askKnowledgeBodySchema,
  response: askKnowledgeResponseSchema,
})

const listBenchmarksContract = contract({
  method: 'GET',
  path: '/v1/benchmarks',
  response: listBenchmarksResponseSchema,
})

const getBenchmarkCaseContract = contract({
  method: 'GET',
  path: '/v1/benchmarks/:caseName',
  params: ['caseName'] as const,
  response: getBenchmarkCaseResponseSchema,
})

const listExperimentFilesContract = contract({
  method: 'GET',
  path: '/v1/experiment/files',
  response: listExperimentFilesResponseSchema,
})

const readExperimentFileContract = contract({
  method: 'GET',
  path: '/v1/experiment/files/:filePath',
  params: ['filePath'] as const,
  pathParams: ['filePath'] as const,
  response: readExperimentFileResponseSchema,
})

const saveExperimentFileContract = contract({
  method: 'POST',
  path: '/v1/experiment/files/:filePath',
  params: ['filePath'] as const,
  pathParams: ['filePath'] as const,
  body: saveExperimentFileBodySchema,
  response: saveExperimentFileResponseSchema,
})

const runExperimentCodeContract = contract({
  method: 'POST',
  path: '/v1/experiment/run',
  body: runExperimentCodeBodySchema,
  response: runExperimentCodeResponseSchema,
})

function normalizeExperimentFilePath(path: string): string {
  return path.startsWith('learning/') ? path : `learning/${path}`
}

export function createSimfeaClient(baseUrl: string, appendLog: (line: string) => void) {
  const { request } = createClient(baseUrl, appendLog)

  return {
    baseUrl,
    connect: () => request(connectContract),
    listRuns: () => request(listRunsContract),
    getRun: (runId: string) => request(getRunContract, { params: { runId } }),
    saveRunNote: (runId: string, note: string, answers?: Record<string, string>) =>
      request(saveNoteContract, {
        params: { runId },
        body: answers ? { answers } : { note },
      }),
    getGuidedQuestions: (runId: string) => request(guidedQuestionsContract, { params: { runId } }),
    generateRunReport: (runId: string) => request(generateReportContract, { params: { runId } }),
    exportLearningRecord: (runId: string, format: string, targetDir?: string) =>
      request(exportLearningContract, {
        params: { runId },
        body: { format, target_dir: targetDir || undefined },
      }),
    probeComputeNode: (alias: string) => request(probeNodeContract, { params: { alias } }),
    probeScheduler: (alias: string) => request(probeSchedulerContract, { params: { alias } }),
    probeSolvers: (alias: string) => request(probeSolversContract, { params: { alias } }),
    listSolvers: () => request(listSolversContract),
    listSolverInstallations: () => request(listSolverInstallationsContract),
    scanSolverInstallation: (alias: string) => request(scanSolverInstallationContract, { params: { alias } }),
    configureSolverExecutable: (alias: string, executable: string) =>
      request(configureSolverExecutableContract, { params: { alias }, body: { executable } }),
    verifySolverInstallation: (alias: string, executable?: string) =>
      request(verifySolverInstallationContract, { params: { alias }, body: { executable } }),
    installSolver: (alias: string) => request(installSolverContract, { params: { alias } }),
    startDemoRun: (alias: string) => request(startDemoRunContract, { params: { alias } }),
    startSlurmDemoRun: (alias: string) => request(startSlurmDemoRunContract, { params: { alias } }),
    startSolverRun: (alias: string, solverAlias: string) =>
      request(startSolverRunContract, { params: { alias, solverAlias } }),
    startFreecadPrepomaxWorkflow: (alias: string) =>
      request(startFreecadPrepomaxWorkflowContract, { params: { alias } }),
    startCustomWorkflow: (
      alias: string,
      steps: (string | { solver: string; params?: Record<string, string> })[]
    ) => request(startCustomWorkflowContract, { params: { alias }, body: { steps } }),
    cancelRun: (runId: string) => request(cancelRunContract, { params: { runId } }),
    listKnowledgeDocuments: () => request(listKnowledgeDocumentsContract),
    deleteKnowledgeDocument: (docId: string) =>
      request(deleteKnowledgeDocumentContract, { params: { docId } }),
    askKnowledge: (question: string, runId?: string, docIds?: string[]) =>
      request(askKnowledgeContract, { body: { question, run_id: runId || '', doc_ids: docIds } }),
    uploadKnowledgeDocument: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await fetch(`${baseUrl}/v1/knowledge/documents`, {
        method: 'POST',
        body: formData,
      })
      if (!resp.ok) {
        const detail = await resp.text().catch(() => '')
        throw new Error(`上传文档失败 (${resp.status}): ${detail}`)
      }
      const json = await resp.json()
      return uploadKnowledgeResponseSchema.parse(json)
    },
    listBenchmarks: () => request(listBenchmarksContract),
    getBenchmarkCase: (caseName: string) => request(getBenchmarkCaseContract, { params: { caseName } }),
    listExperimentFiles: async () => {
      const response = await request(listExperimentFilesContract)
      return {
        ...response,
        data: {
          ...response.data,
          files: response.data.files.map((file) => ({
            ...file,
            path: normalizeExperimentFilePath(file.path),
          })),
        },
      }
    },
    readExperimentFile: (filePath: string) => request(readExperimentFileContract, { params: { filePath } }),
    saveExperimentFile: (filePath: string, content: string) =>
      request(saveExperimentFileContract, { params: { filePath }, body: { content } }),
    runExperimentCode: (opts: { code?: string; file_path?: string }) =>
      request(runExperimentCodeContract, { body: opts }),
  }
}

export type SimfeaClient = ReturnType<typeof createSimfeaClient>
