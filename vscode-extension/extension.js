// ROCmPorter VS Code extension — CUDA lock-in diagnostics, HIP hovers,
// quick fixes, and one-click hipify. Plain JS, no build step.
const vscode = require('vscode')
const fs = require('fs')
const path = require('path')

// Compact CUDA -> HIP mapping (mirror of the backend hipify core).
const MAP = [
  ['cudaMallocManaged', 'hipMallocManaged'],
  ['cudaMallocHost', 'hipHostMalloc'],
  ['cudaMallocAsync', 'hipMallocAsync'],
  ['cudaMalloc', 'hipMalloc'],
  ['cudaFreeHost', 'hipHostFree'],
  ['cudaFreeAsync', 'hipFreeAsync'],
  ['cudaFree', 'hipFree'],
  ['cudaMemcpyAsync', 'hipMemcpyAsync'],
  ['cudaMemcpyToSymbol', 'hipMemcpyToSymbol'],
  ['cudaMemcpy2D', 'hipMemcpy2D'],
  ['cudaMemcpy', 'hipMemcpy'],
  ['cudaMemsetAsync', 'hipMemsetAsync'],
  ['cudaMemset', 'hipMemset'],
  ['cudaMemcpyHostToDevice', 'hipMemcpyHostToDevice'],
  ['cudaMemcpyDeviceToHost', 'hipMemcpyDeviceToHost'],
  ['cudaMemcpyDeviceToDevice', 'hipMemcpyDeviceToDevice'],
  ['cudaMemcpyDefault', 'hipMemcpyDefault'],
  ['cudaGetDeviceProperties', 'hipGetDeviceProperties'],
  ['cudaGetDeviceCount', 'hipGetDeviceCount'],
  ['cudaGetDevice', 'hipGetDevice'],
  ['cudaSetDevice', 'hipSetDevice'],
  ['cudaDeviceSynchronize', 'hipDeviceSynchronize'],
  ['cudaDeviceReset', 'hipDeviceReset'],
  ['cudaDeviceProp', 'hipDeviceProp_t'],
  ['cudaStreamCreateWithFlags', 'hipStreamCreateWithFlags'],
  ['cudaStreamCreate', 'hipStreamCreate'],
  ['cudaStreamDestroy', 'hipStreamDestroy'],
  ['cudaStreamSynchronize', 'hipStreamSynchronize'],
  ['cudaStream_t', 'hipStream_t'],
  ['cudaEventCreate', 'hipEventCreate'],
  ['cudaEventDestroy', 'hipEventDestroy'],
  ['cudaEventRecord', 'hipEventRecord'],
  ['cudaEventSynchronize', 'hipEventSynchronize'],
  ['cudaEventElapsedTime', 'hipEventElapsedTime'],
  ['cudaEvent_t', 'hipEvent_t'],
  ['cudaGetErrorString', 'hipGetErrorString'],
  ['cudaGetLastError', 'hipGetLastError'],
  ['cudaSuccess', 'hipSuccess'],
  ['cudaError_t', 'hipError_t'],
  ['cublasCreate', 'hipblasCreate'],
  ['cublasDestroy', 'hipblasDestroy'],
  ['cublasSgemm', 'hipblasSgemm'],
  ['cublasHandle_t', 'hipblasHandle_t'],
  ['curandCreateGenerator', 'hiprandCreateGenerator'],
  ['curand_init', 'hiprand_init'],
  ['curand_uniform', 'hiprand_uniform'],
  ['cufftPlan1d', 'hipfftPlan1d'],
  ['cufftExecC2C', 'hipfftExecC2C'],
  ['ncclAllReduce', 'rcclAllReduce'],
]
const HEADER_MAP = [
  ['<cuda_runtime.h>', '<hip/hip_runtime.h>'],
  ['<cuda.h>', '<hip/hip_runtime.h>'],
  ['<cuda_fp16.h>', '<hip/hip_fp16.h>'],
  ['<cublas_v2.h>', '<hipblas/hipblas.h>'],
  ['<curand.h>', '<hiprand/hiprand.h>'],
  ['<cufft.h>', '<hipfft/hipfft.h>'],
  ['<cudnn.h>', '<miopen/miopen.h>'],
  ['<nccl.h>', '<rccl/rccl.h>'],
]
const MAP_LOOKUP = new Map(MAP)
// Advisory-only signals (no safe mechanical fix).
const ADVISORY = [
  ['torch\\.cuda\\b', 'Runs on ROCm builds of PyTorch too, but pins intent to CUDA — verify device strings.'],
  ['\\bnvcc\\b', 'NVIDIA compiler — use hipcc on ROCm.'],
  ['CUDAExtension', 'PyTorch CUDA build extension — ROCm builds hipify this; verify setup.py.'],
  ['\\bcudnn\\w*', 'cuDNN — MIOpen is the ROCm equivalent.'],
]

const LANGS = new Set(['c', 'cpp', 'cuda-cpp', 'cuda', 'python', 'cmake', 'dockerfile', 'makefile'])
const TOKEN_RE = new RegExp('\\b(' + MAP.map(([c]) => c).join('|') + ')\\b', 'g')

let diagnostics
let enabled = true

function relevant(doc) {
  if (doc.uri.scheme !== 'file') return false
  if (LANGS.has(doc.languageId)) return true
  return /\.(cu|cuh|hip)$/.test(doc.fileName)
}

function refresh(doc) {
  if (!diagnostics || !relevant(doc)) return
  if (!enabled) {
    diagnostics.delete(doc.uri)
    return
  }
  const text = doc.getText()
  const items = []
  let m
  TOKEN_RE.lastIndex = 0
  while ((m = TOKEN_RE.exec(text)) !== null) {
    const hip = MAP_LOOKUP.get(m[1])
    const range = new vscode.Range(doc.positionAt(m.index), doc.positionAt(m.index + m[1].length))
    const d = new vscode.Diagnostic(
      range,
      `CUDA lock-in: ${m[1]} → HIP equivalent: ${hip}`,
      vscode.DiagnosticSeverity.Warning,
    )
    d.source = 'ROCmPorter'
    d.code = m[1]
    items.push(d)
  }
  for (const [pat, msg] of ADVISORY) {
    const re = new RegExp(pat, 'g')
    while ((m = re.exec(text)) !== null) {
      const range = new vscode.Range(doc.positionAt(m.index), doc.positionAt(m.index + m[0].length))
      const d = new vscode.Diagnostic(range, `CUDA lock-in: ${m[0]} — ${msg}`, vscode.DiagnosticSeverity.Information)
      d.source = 'ROCmPorter'
      items.push(d)
    }
  }
  diagnostics.set(doc.uri, items)
}

function hipifyText(text) {
  let out = text
  let count = 0
  for (const [cudaHdr, hipHdr] of HEADER_MAP) {
    const before = out
    out = out.split(cudaHdr).join(hipHdr)
    if (out !== before) count++
  }
  for (const [cuda, hip] of MAP) {
    const re = new RegExp('\\b' + cuda + '\\b', 'g')
    if (re.test(out)) {
      out = out.replace(re, hip)
      count++
    }
  }
  return { out, count }
}

function findRepoUrl() {
  const folders = vscode.workspace.workspaceFolders
  if (!folders || !folders.length) return null
  try {
    const cfg = fs.readFileSync(path.join(folders[0].uri.fsPath, '.git', 'config'), 'utf8')
    const match = cfg.match(/url\s*=\s*(\S+)/)
    if (!match) return null
    let url = match[1].replace(/^git@github\.com:/, 'https://github.com/').replace(/\.git$/, '')
    return url.startsWith('https://github.com/') ? url : null
  } catch {
    return null
  }
}

function activate(context) {
  diagnostics = vscode.languages.createDiagnosticCollection('rocmporter')
  enabled = vscode.workspace.getConfiguration('rocmporter').get('diagnostics.enabled', true)

  context.subscriptions.push(
    diagnostics,
    vscode.workspace.onDidOpenTextDocument(refresh),
    vscode.workspace.onDidChangeTextDocument((e) => refresh(e.document)),
    vscode.window.onDidChangeActiveTextEditor((ed) => ed && refresh(ed.document)),

    vscode.languages.registerHoverProvider(
      [{ scheme: 'file' }],
      {
        provideHover(doc, pos) {
          const range = doc.getWordRangeAtPosition(pos, /[A-Za-z_][A-Za-z0-9_]*/)
          if (!range) return
          const word = doc.getText(range)
          const hip = MAP_LOOKUP.get(word)
          if (!hip) return
          const md = new vscode.MarkdownString()
          md.appendMarkdown(`**ROCmPorter** · CUDA → HIP\n\n\`${word}\` → \`${hip}\`\n\n`)
          md.appendMarkdown(`[Scan this repo for full lock-in report](https://rocmporter-agent.vercel.app)`)
          return new vscode.Hover(md, range)
        },
      },
    ),

    vscode.languages.registerCodeActionsProvider(
      [{ scheme: 'file' }],
      {
        provideCodeActions(doc, _range, ctx) {
          const actions = []
          for (const d of ctx.diagnostics) {
            if (d.source !== 'ROCmPorter' || !d.code) continue
            const hip = MAP_LOOKUP.get(String(d.code))
            if (!hip) continue
            const fix = new vscode.CodeAction(`Replace with ${hip}`, vscode.CodeActionKind.QuickFix)
            fix.edit = new vscode.WorkspaceEdit()
            fix.edit.replace(doc.uri, d.range, hip)
            fix.diagnostics = [d]
            fix.isPreferred = true
            actions.push(fix)
          }
          return actions
        },
      },
      { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] },
    ),

    vscode.commands.registerCommand('rocmporter.hipifyFile', async () => {
      const editor = vscode.window.activeTextEditor
      if (!editor) return
      const { out, count } = hipifyText(editor.document.getText())
      if (!count) {
        vscode.window.showInformationMessage('ROCmPorter: no mechanical CUDA→HIP mappings found in this file.')
        return
      }
      const full = new vscode.Range(
        editor.document.positionAt(0),
        editor.document.positionAt(editor.document.getText().length),
      )
      await editor.edit((b) => b.replace(full, out))
      vscode.window.showInformationMessage(
        `ROCmPorter: applied ${count} deterministic CUDA→HIP mapping group(s). Review the diff before committing.`,
      )
    }),

    vscode.commands.registerCommand('rocmporter.scanRepo', () => {
      const base = vscode.workspace.getConfiguration('rocmporter').get('appUrl', 'https://rocmporter-agent.vercel.app')
      const repo = findRepoUrl()
      const url = repo ? `${base}/app?repo=${encodeURIComponent(repo)}` : `${base}/app`
      vscode.env.openExternal(vscode.Uri.parse(url))
    }),

    vscode.commands.registerCommand('rocmporter.toggleDiagnostics', () => {
      enabled = !enabled
      vscode.window.showInformationMessage(`ROCmPorter diagnostics ${enabled ? 'enabled' : 'disabled'}.`)
      vscode.workspace.textDocuments.forEach(refresh)
    }),
  )

  vscode.workspace.textDocuments.forEach(refresh)
}

function deactivate() {}

module.exports = { activate, deactivate }
