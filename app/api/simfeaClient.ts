export type HttpMethod = 'GET' | 'POST';

export interface SimfeaClient {
  connect(): Promise<any>;
  listRuns(): Promise<any>;
  getRun(runId: string): Promise<any>;
  saveRunNote(runId: string, note: string): Promise<any>;
  generateRunReport(runId: string): Promise<any>;
  exportLearningRecord(runId: string, format: string, targetDir?: string): Promise<any>;
  probeComputeNode(alias: string): Promise<any>;
  probeScheduler(alias: string): Promise<any>;
  startDemoRun(alias: string): Promise<any>;
  startSlurmDemoRun(alias: string): Promise<any>;
  cancelRun(runId: string): Promise<any>;
}

const createRequester = (baseUrl: string, appendLog: (line: string) => void) => {
  return async (endpoint: string, method: HttpMethod = 'GET', body?: unknown): Promise<any> => {
    const url = `${baseUrl}/${endpoint}`;
    try {
      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!response.ok) {
        throw new Error(`request failed: ${response.status} ${await response.text()}`);
      }
      const json = await response.json();
      if (json?.message) {
        appendLog(`[服务响应] ${json.message}`);
      }
      return json;
    } catch (error: any) {
      appendLog(`[服务响应] ${error}`);
      throw error;
    }
  };
};

export const createSimfeaClient = (baseUrl: string, appendLog: (line: string) => void): SimfeaClient => {
  const request = createRequester(baseUrl, appendLog);
  return {
    connect: () => request('v1/connect'),
    listRuns: () => request('v1/runs'),
    getRun: (runId: string) => request(`v1/runs/${runId}`),
    saveRunNote: (runId: string, note: string) => request(`v1/runs/${runId}/note`, 'POST', { note }),
    generateRunReport: (runId: string) => request(`v1/runs/${runId}/report`),
    exportLearningRecord: (runId: string, format: string, targetDir?: string) =>
      request(`v1/runs/${runId}/learning-export`, 'POST', {
        format,
        target_dir: targetDir || undefined,
      }),
    probeComputeNode: (alias: string) => request(`v1/compute-nodes/${alias}/probe`),
    probeScheduler: (alias: string) => request(`v1/compute-nodes/${alias}/scheduler-probe`),
    startDemoRun: (alias: string) => request(`v1/runs/${alias}/demo`, 'POST'),
    startSlurmDemoRun: (alias: string) => request(`v1/runs/${alias}/slurm-demo`, 'POST'),
    cancelRun: (runId: string) => request(`v1/runs/${runId}/cancel`, 'POST'),
  };
};
