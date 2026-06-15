import { computed, ref } from 'vue'

export interface ExpFile {
  path: string
  name: string
  dir: string
  size: number
}

export interface FileGroup {
  dir: string
  docs: ExpFile[]
  code: ExpFile[]
}

export function fileIcon(name: string): string {
  if (name.endsWith('.ipynb')) return '📓'
  if (name.endsWith('.py')) return '🐍'
  if (name.endsWith('.inp')) return '📐'
  if (name.endsWith('.json')) return '📋'
  return '📄'
}

export function useExperimentFiles(apiBaseUrl: string) {
  const baseUrl = apiBaseUrl.replace(/\/+$/, '')
  const files = ref<ExpFile[]>([])
  const selectedFile = ref<ExpFile | null>(null)
  const editorContent = ref('')
  const consoleOutput = ref('')
  const running = ref(false)
  const modified = ref(false)
  const savedPath = ref('')
  const preview = ref(false)
  const loading = ref(false)

  const isMarkdown = computed(() => selectedFile.value?.name.endsWith('.md'))

  const isCodeFile = computed(() => {
    const name = selectedFile.value?.name ?? ''
    return /\.(py|json|inp|txt|log|yaml|yml|toml|cfg|ini)$/i.test(name)
  })

  const fileGroups = computed(() => {
    const map: Record<string, ExpFile[]> = {}
    for (const f of files.value) {
      if (f.path.startsWith('learning/research/')) continue
      if (!map[f.dir]) map[f.dir] = []
      map[f.dir].push(f)
    }
    return Object.entries(map).map(([dir, fs]) => {
      const docs = fs.filter((f) => f.name.endsWith('.md'))
      const code = fs.filter((f) => !f.name.endsWith('.md'))
      return { dir: dir.replace(/^learning\//, ''), docs, code } as FileGroup
    })
  })

  async function fetchFiles() {
    loading.value = true
    try {
      const r = await fetch(`${baseUrl}/v1/experiment/files`)
      const j = await r.json()
      files.value = (j.data?.files || []) as ExpFile[]
    } catch {
      /* */
    }
    loading.value = false
  }

  async function openFile(f: ExpFile) {
    if (modified.value && !confirm('当前文件未保存，是否放弃更改？')) return
    loading.value = true
    try {
      const r = await fetch(`${baseUrl}/v1/experiment/files/${encodeURI(f.path)}`)
      const j = await r.json()
      editorContent.value = j.data.content as string
      selectedFile.value = f
      savedPath.value = f.path
      modified.value = false
      consoleOutput.value = ''
    } catch {
      /* */
    }
    loading.value = false
  }

  async function saveFile() {
    if (!selectedFile.value) return
    try {
      await fetch(`${baseUrl}/v1/experiment/files/${encodeURI(savedPath.value)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: editorContent.value }),
      })
      modified.value = false
      consoleOutput.value = `已保存 — ${new Date().toLocaleTimeString()}\n${consoleOutput.value}`
    } catch {
      /* */
    }
  }

  function newFile() {
    if (modified.value && !confirm('当前文件未保存，是否放弃更改？')) return
    const name = prompt('文件名:', 'experiment.py')
    if (!name) return
    const path = `learning/experiments/${name}`
    selectedFile.value = { path, name, dir: 'learning/experiments', size: 0 }
    savedPath.value = path
    editorContent.value = '# New experiment\n\n'
    modified.value = true
    consoleOutput.value = ''
  }

  async function runFile() {
    if (!selectedFile.value) return
    if (modified.value) await saveFile()
    running.value = true
    consoleOutput.value = `$ python ${selectedFile.value.name}\n`
    try {
      const r = await fetch(`${baseUrl}/v1/experiment/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: savedPath.value }),
      })
      const j = await r.json()
      const d = j.data as Record<string, unknown>
      consoleOutput.value += (d.stdout as string) || ''
      if (d.stderr) consoleOutput.value += `\n${d.stderr}`
      if (!d.stdout && !d.stderr) consoleOutput.value += `(exit ${d.exit_code})\n`
    } catch (err) {
      consoleOutput.value += `Error: ${err}\n`
    } finally {
      running.value = false
    }
  }

  function onEditorKeydown(e: KeyboardEvent) {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault()
      saveFile()
    }
    if (e.key === 'F5') {
      e.preventDefault()
      runFile()
    }
  }

  return {
    files,
    selectedFile,
    editorContent,
    consoleOutput,
    running,
    modified,
    savedPath,
    preview,
    loading,
    isMarkdown,
    isCodeFile,
    fileGroups,
    fetchFiles,
    openFile,
    saveFile,
    newFile,
    runFile,
    onEditorKeydown,
  }
}
