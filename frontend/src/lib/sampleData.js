const SAMPLE_SCAN_ID = 'sample_extension_cpp'
const SAMPLE_PATCH_ID = 'sample_patch_setup_py_rocm'

export const sampleScan = {
  scanId: SAMPLE_SCAN_ID,
  status: 'completed',
  progress: {
    stage: 'sample report loaded',
    percent: 100,
  },
  repoUrl: 'https://github.com/pytorch/extension-cpp',
  error: null,
}

export const demoRepositories = [
  {
    name: 'extension-cpp',
    url: 'https://github.com/pytorch/extension-cpp',
    note: 'Recommended first demo: small PyTorch C++/CUDA extension.',
  },
  {
    name: 'cuda-samples',
    url: 'https://github.com/NVIDIA/cuda-samples',
    note: 'CUDA-heavy benchmark for scanner coverage.',
  },
  {
    name: 'cupy',
    url: 'https://github.com/cupy/cupy',
    note: 'Large GPU Python library for stress testing findings.',
  },
  {
    name: 'flash-attention',
    url: 'https://github.com/Dao-AILab/flash-attention',
    note: 'Advanced CUDA kernels and package signals.',
  },
]

export const benchmarkProof = {
  runName: 'quality-check-expanded-v1',
  summaryPath: 'work/benchmark-runs/quality-check-expanded-v1/summary.json',
  headline: '4 export-ready review bundles',
  summary:
    'Focused benchmark run completed across PyTorch extension and flash-attention build paths with 0 high-risk outputs. Apply is intentionally blocked until a live workspace and ROCm hardware validation are available.',
  totals: [
    { label: 'Cases', value: '4/4' },
    { label: 'Export ready', value: '4' },
    { label: 'High risk', value: '0' },
    { label: 'Apply ready', value: '0' },
  ],
  cases: [
    {
      name: 'extension-cpp',
      target: 'extension_cpp/setup.py',
      risk: 'low',
    },
    {
      name: 'extension-cpp-stable',
      target: 'extension_cpp_stable/setup.py',
      risk: 'low',
    },
    {
      name: 'flash-attention',
      target: 'csrc/fused_dense_lib/setup.py',
      risk: 'medium',
    },
    {
      name: 'flash-attention-layer-norm',
      target: 'csrc/layer_norm/setup.py',
      risk: 'medium',
    },
  ],
}

export const localFirstFacts = ['Local Ollama', 'No cloud LLM API', 'CPU syntax checks', 'Offline export bundle', 'Self-hosted patch CI']

export const sampleReport = {
  repo: {
    url: 'https://github.com/pytorch/extension-cpp',
    name: 'extension-cpp',
    defaultBranch: 'main',
  },
  summary: {
    portabilityScore: 54,
    riskLevel: 'medium',
    estimatedEffort: '3-5 days',
    scanCompletedAt: '2026-07-01T05:00:00.000Z',
  },
  findings: [
    {
      id: 'cuda_build_config',
      severity: 'high',
      title: 'Build configuration is tied to CUDA or NVCC',
      details: 'The extension build script checks CUDA availability and compiles with CUDA-specific extension helpers.',
      recommendation: 'Add a ROCm/HIP branch that uses ROCm-aware build flags and avoids hard CUDA-only assumptions.',
      confidence: 'high',
      evidence: [
        {
          path: 'extension_cpp/setup.py',
          lineStart: 42,
          lineEnd: 48,
          matchText: 'CUDAExtension',
          snippet:
            'from torch.utils.cpp_extension import BuildExtension, CUDAExtension\n\nsetup(\n    name="extension_cpp",\n    ext_modules=[CUDAExtension("extension_cpp", sources)],\n)',
        },
      ],
    },
    {
      id: 'cuda_runtime_headers',
      severity: 'high',
      title: 'CUDA-only headers or libraries referenced',
      details: 'Source files include CUDA runtime headers that need HIP compatibility review before AMD execution.',
      recommendation: 'Map CUDA runtime calls to HIP equivalents and validate compilation on ROCm hardware when available.',
      confidence: 'high',
      evidence: [
        {
          path: 'extension_cpp/csrc/cuda/muladd.cu',
          lineStart: 1,
          lineEnd: 5,
          matchText: 'cuda_runtime.h',
          snippet: '#include <cuda_runtime.h>\n#include <torch/extension.h>\n\n__global__ void muladd_kernel(...) { }',
        },
      ],
    },
    {
      id: 'nvidia_container_signals',
      severity: 'medium',
      title: 'Container or runtime scripts assume NVIDIA GPUs',
      details: 'CI scripts include NVIDIA-oriented runtime checks that do not prove ROCm readiness.',
      recommendation: 'Add ROCm validation commands and keep NVIDIA-specific checks separate from AMD migration proof.',
      confidence: 'medium',
      evidence: [
        {
          path: '.github/workflows/tests.yml',
          lineStart: 28,
          lineEnd: 31,
          matchText: 'nvidia-smi',
          snippet: '- name: Show GPU\n  run: nvidia-smi || true\n\n- name: Run tests',
        },
      ],
    },
  ],
  build: {
    languages: ['CUDA C++', 'Python', 'C++'],
    buildSystems: ['Python Packaging', 'GitHub Actions'],
    gpuSignals: ['extension_cpp/setup.py', 'extension_cpp/csrc/cuda/muladd.cu', '.github/workflows/tests.yml'],
  },
  nextSteps: [
    'Replace CUDA-specific extension setup with a ROCm/HIP-aware build path.',
    'Validate the generated patch with Python syntax checks and diff replay.',
    'Run optional AMD hardware validation when ROCm access becomes available.',
  ],
  coverage: {
    totalFiles: 41,
    scannedFiles: 34,
    skippedLargeFiles: 0,
    skippedDirectories: ['.git', 'build', 'dist', 'node_modules'],
    supportedTextExtensions: ['.py', '.cu', '.cuh', '.cpp', '.h', '.yml'],
  },
  rulesetVersion: '2026.06.29',
}

export function buildSamplePatch(evidencePath = 'extension_cpp/setup.py', findingId = 'cuda_build_config') {
  return {
    patchId: SAMPLE_PATCH_ID,
    scanId: SAMPLE_SCAN_ID,
    findingId,
    evidencePath,
    model: 'qwen2.5-coder:latest',
    status: 'completed',
    stage: 'sample patch ready',
    createdAt: '2026-07-01T05:01:00.000Z',
    updatedAt: '2026-07-01T05:02:00.000Z',
    patchMode: 'partial',
    rationale:
      'The patch adds a ROCm-aware build guard while keeping PyTorch CUDAExtension wiring intact for review. This is a conservative partial artifact, not full migration proof, so workspace apply stays blocked until live validation is complete.',
    diff:
      'diff --git a/extension_cpp/setup.py b/extension_cpp/setup.py\n' +
      '--- a/extension_cpp/setup.py\n' +
      '+++ b/extension_cpp/setup.py\n' +
      '@@ -1,7 +1,13 @@\n' +
      '-from torch.utils.cpp_extension import BuildExtension, CUDAExtension\n' +
      '+import os\n' +
      '+import torch\n' +
      '+from torch.utils.cpp_extension import BuildExtension, CUDAExtension\n' +
      '+\n' +
      '+USE_ROCM = os.getenv("USE_ROCM") == "1" or getattr(torch.version, "hip", None) is not None\n' +
      '+define_macros = [("USE_ROCM", "1")] if USE_ROCM else []\n' +
      ' \n' +
      ' setup(\n' +
      '     name="extension_cpp",\n' +
      '-    ext_modules=[CUDAExtension("extension_cpp", sources)],\n' +
      '+    ext_modules=[CUDAExtension("extension_cpp", sources, define_macros=define_macros)],\n' +
      '     cmdclass={"build_ext": BuildExtension},\n' +
      ' )\n',
    savedPatchPath: 'work/patches/sample_patch_setup_py_rocm/setup.py.diff',
    savedPatchedFilePath: 'work/patches/sample_patch_setup_py_rocm/patched/extension_cpp/setup.py',
    reviewRequired: true,
    warnings: [
      {
        code: 'partial_patch_scope',
        severity: 'medium',
        message: 'This patch covers one evidence file only and must be reviewed before it is treated as a complete ROCm migration.',
      },
      {
        code: 'rocm_hardware_validation_pending',
        severity: 'medium',
        message: 'ROCm hardware validation is still required before merging into a production branch.',
      },
    ],
    validation: {
      state: 'passed',
      tool: 'python -m py_compile',
      summary: 'Patched setup.py syntax check passed in the scanned workspace snapshot.',
      details: ['Unified diff replay succeeded.', 'No model control text was detected in the patch output.'],
    },
    riskAssessment: {
      score: 42,
      level: 'medium',
      summary: 'The artifact is export-ready for review, while workspace apply remains blocked until broader ROCm validation is available.',
      reasons: ['Partial patch scope.', 'Build system behavior changes.', 'Hardware execution proof is pending.'],
      checklist: [
        'Review generated diff.',
        'Confirm this is only a single-file migration aid.',
        'Confirm CUDAExtension remains intentional for PyTorch ROCm builds.',
        'Run syntax and diff replay checks.',
        'Run optional AMD/ROCm validation job.',
      ],
      factors: [],
    },
    changedLineCount: 7,
    changedHunkCount: 1,
    sourceFilePath: 'work/patches/source/sample_patch_setup_py_rocm/extension_cpp/setup.py',
    sourceFileSha256: 'sample-sha256-source-file',
  }
}

export const sampleVerification = {
  receiptId: 'sample_receipt_setup_py_rocm',
  scanId: SAMPLE_SCAN_ID,
  patchId: SAMPLE_PATCH_ID,
  generatedAt: '2026-07-01T05:03:00.000Z',
  state: 'warning',
  summary: 'Patch artifacts are internally consistent and export-ready as a review artifact. Workspace apply remains blocked until a live repository flow is verified.',
  applyReady: false,
  exportReady: true,
  artifactHashes: {
    diff: 'sample-sha256-diff',
    patchedFile: 'sample-sha256-patched-file',
  },
  checks: [
    {
      code: 'diff_replay',
      label: 'Diff replay',
      state: 'passed',
      message: 'The generated diff applies cleanly to the source snapshot.',
    },
    {
      code: 'semantic_sanity',
      label: 'ROCm semantic sanity',
      state: 'passed',
      message: 'No invented PyTorch ROCm extension APIs were introduced.',
    },
    {
      code: 'rocm_hardware',
      label: 'ROCm hardware validation',
      state: 'warning',
      message: 'No AMD GPU runner was attached for this sample run.',
    },
  ],
  savedReceiptPath: 'work/patches/sample_patch_setup_py_rocm/patch-verification.json',
}

export const sampleExportBundle = {
  exportId: 'sample_export_bundle',
  scanId: SAMPLE_SCAN_ID,
  patchId: SAMPLE_PATCH_ID,
  createdAt: '2026-07-01T05:04:00.000Z',
  rootPath: 'work/exports/sample_export_bundle',
  warnings: ['Sample bundle paths are illustrative. Run a live export to download real artifacts.'],
  files: [
    { kind: 'html_report', label: 'HTML Report', path: 'index.html' },
    { kind: 'zip_bundle', label: 'Zip Bundle', path: 'bundle.zip' },
    { kind: 'github_review_markdown', label: 'GitHub Review Markdown', path: 'github-review.md' },
    { kind: 'patch_diff', label: 'Patch Diff', path: 'patches/setup.py.diff' },
    { kind: 'checksums', label: 'SHA256 Checksums', path: 'SHA256SUMS.txt' },
  ],
}

export const sampleGitHubReview = {
  reviewId: 'sample_github_review',
  scanId: SAMPLE_SCAN_ID,
  patchId: SAMPLE_PATCH_ID,
  repository: 'pytorch/extension-cpp',
  pullRequestNumber: 42,
  createdAt: '2026-07-01T05:05:00.000Z',
  riskScore: 42,
  riskLevel: 'medium',
  verificationState: 'warning',
  applyReady: false,
  exportReady: true,
  reviewReady: true,
  draftOnly: false,
  summary: 'Sample review: conservative ROCm build-path aid generated; hardware validation remains the merge gate.',
  warnings: ['Sample review was not posted to GitHub.'],
  commentBody:
    '## ROCmPorter Review\n\nThis patch adds a ROCm-aware build guard while keeping PyTorch CUDAExtension wiring reviewable.\n\n- Verification state: `warning`\n- Export ready: `true`\n- Apply ready: `false`\n\n> Review artifact: export is ready, but workspace apply remains blocked by verification.\n\nMerge checklist:\n- Review the diff\n- Run syntax validation\n- Confirm CUDAExtension is intentional for PyTorch ROCm builds\n- Run ROCm hardware validation when available',
  savedMarkdownPath: 'work/exports/sample_export_bundle/github-review.md',
  savedJsonPath: 'work/exports/sample_export_bundle/github-review.json',
  savedInlineCommentsPath: 'work/exports/sample_export_bundle/github-review-inline-comments.json',
  inlineCommentsCount: 1,
  savedPrSafeInlineCommentsPath: 'work/exports/sample_export_bundle/github-review-inline-comments-pr-safe.json',
  prSafeInlineCommentsCount: 1,
  posted: false,
  postUrl: null,
  postError: null,
}

export function buildSampleApplyResult() {
  return {
    applyId: 'sample_apply_setup_py_rocm',
    scanId: SAMPLE_SCAN_ID,
    patchId: SAMPLE_PATCH_ID,
    status: 'applied',
    targetFilePath: 'work/temp-repos/sample_extension_cpp/extension_cpp/setup.py',
    workspaceRoot: 'work/temp-repos/sample_extension_cpp',
    backupFilePath: 'work/backups/sample_apply_setup_py_rocm/setup.py',
    appliedFilePath: 'work/applied/sample_apply_setup_py_rocm/setup.py',
    createdAt: '2026-07-01T05:06:00.000Z',
    updatedAt: '2026-07-01T05:06:00.000Z',
    rollbackAvailable: true,
    rollbackReason: null,
    error: null,
  }
}
