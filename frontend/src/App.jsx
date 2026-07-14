import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  applyPatch,
  createExport,
  createGitHubReview,
  createPatch,
  createScan,
  getApiUrl,
  getHealth,
  getOllamaStatus,
  getPatches,
  getPatch,
  getReport,
  getScan,
  repairPatch,
  rollbackPatchApply,
  verifyPatch,
  warmOllamaModel,
} from './lib/api'
import {
  benchmarkProof,
  buildSampleApplyResult,
  buildSamplePatch,
  demoRepositories,
  localFirstFacts,
  sampleExportBundle,
  sampleGitHubReview,
  sampleReport,
  sampleScan,
  sampleVerification,
} from './lib/sampleData'

const DEFAULT_MODEL = 'qwen2.5-coder'
const FALLBACK_MODEL = `${DEFAULT_MODEL}:latest`
const EXPORT_FORMATS = ['json', 'markdown', 'diff', 'html', 'zip', 'github']

const STATUS_LABELS = {
  idle: 'Idle',
  queued: 'Queued',
  running: 'Running',
  cloning: 'Cloning',
  scanning: 'Scanning',
  generation: 'Generating',
  completed: 'Complete',
  failed: 'Failed',
  applied: 'Applied',
  rolled_back: 'Rolled back',
  waiting: 'Waiting',
}

const WARNING_TITLES = {
  response_artifact_leak: 'Model output leak detected',
  partial_patch: 'Partial patch',
  validation_skipped: 'Validation skipped',
}

const ACRONYM_FIXES = [
  [/\brocm\b/gi, 'ROCm'],
  [/\bcuda\b/gi, 'CUDA'],
  [/\bgithub\b/gi, 'GitHub'],
  [/\bnvidia\b/gi, 'NVIDIA'],
  [/\bapi\b/gi, 'API'],
]

function humanizeStatus(value) {
  if (!value) {
    return 'Idle'
  }
  const key = String(value).toLowerCase()
  if (STATUS_LABELS[key]) {
    return STATUS_LABELS[key]
  }
  const spaced = key.replaceAll('_', ' ')
  let label = spaced.charAt(0).toUpperCase() + spaced.slice(1)
  for (const [pattern, replacement] of ACRONYM_FIXES) {
    label = label.replace(pattern, replacement)
  }
  return label
}

function warningTitle(warning) {
  if (warning.code && WARNING_TITLES[warning.code]) {
    return WARNING_TITLES[warning.code]
  }
  if (warning.code) {
    return humanizeStatus(warning.code)
  }
  return `${humanizeStatus(warning.severity)} warning`
}

function App() {
  const [repoUrl, setRepoUrl] = useState('https://github.com/pytorch/extension-cpp')
  const [scan, setScan] = useState(null)
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [activeFilter, setActiveFilter] = useState('all')
  const [models, setModels] = useState([{ name: FALLBACK_MODEL }])
  const [selectedModel, setSelectedModel] = useState(FALLBACK_MODEL)
  const [ollamaStatus, setOllamaStatus] = useState(null)
  const [ollamaError, setOllamaError] = useState('')
  const [isRefreshingOllama, setIsRefreshingOllama] = useState(false)
  const [isWarmingModel, setIsWarmingModel] = useState(false)
  const [patchJob, setPatchJob] = useState(null)
  const [patchError, setPatchError] = useState('')
  const [isRequestingPatch, setIsRequestingPatch] = useState(false)
  const [pendingPatchTarget, setPendingPatchTarget] = useState(null)
  const [patchApply, setPatchApply] = useState(null)
  const [applyError, setApplyError] = useState('')
  const [isApplyingPatch, setIsApplyingPatch] = useState(false)
  const [isRepairingPatch, setIsRepairingPatch] = useState(false)
  const [isRollingBackPatch, setIsRollingBackPatch] = useState(false)
  const [patchVerification, setPatchVerification] = useState(null)
  const [verificationError, setVerificationError] = useState('')
  const [isVerifyingPatch, setIsVerifyingPatch] = useState(false)
  const [exportBundle, setExportBundle] = useState(null)
  const [exportError, setExportError] = useState('')
  const [isExporting, setIsExporting] = useState(false)
  const [githubReview, setGitHubReview] = useState(null)
  const [githubReviewError, setGitHubReviewError] = useState('')
  const [isGeneratingReview, setIsGeneratingReview] = useState(false)
  const [githubPrNumber, setGitHubPrNumber] = useState('')
  const [shouldPostReview, setShouldPostReview] = useState(false)
  const [isDemoMode, setIsDemoMode] = useState(false)
  const [apiHealth, setApiHealth] = useState('checking')
  const [toast, setToast] = useState(null)
  const verifyingPatchIdRef = useRef(null)
  const patchPanelRef = useRef(null)
  const patchInFlight = patchJob?.status === 'queued' || patchJob?.status === 'running'

  const applyOllamaState = useCallback(
    (nextStatus) => {
      setOllamaStatus(nextStatus)
      setOllamaError(nextStatus.reachable ? '' : nextStatus.error ?? '')

      if (nextStatus.models?.length) {
        setModels(nextStatus.models)
        setSelectedModel((current) => chooseSelectedModel(current, nextStatus.models, nextStatus.preferredModel?.resolvedName))
        return
      }

      setModels([{ name: selectedModel || FALLBACK_MODEL }])
      setSelectedModel((current) => current || FALLBACK_MODEL)
    },
    [selectedModel],
  )

  useEffect(() => {
    let cancelled = false

    async function loadOllamaState() {
      try {
        const nextStatus = await getOllamaStatus(selectedModel)
        if (!cancelled) {
          applyOllamaState(nextStatus)
        }
      } catch (statusError) {
        if (!cancelled) {
          const fallbackModelName = selectedModel || FALLBACK_MODEL
          const fallbackStatus = buildFallbackOllamaStatus(selectedModel, statusError.message)
          setOllamaStatus(fallbackStatus)
          setOllamaError(statusError.message)
          setModels([{ name: fallbackModelName }])
          setSelectedModel(fallbackModelName)
        }
      }
    }

    loadOllamaState()
    const intervalId = window.setInterval(loadOllamaState, patchInFlight || isWarmingModel ? 5000 : 20000)

    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [applyOllamaState, isWarmingModel, patchInFlight, selectedModel])

  useEffect(() => {
    let cancelled = false

    async function checkApiHealth() {
      try {
        await getHealth()
        if (!cancelled) {
          setApiHealth('ok')
        }
      } catch {
        if (!cancelled) {
          setApiHealth('error')
        }
      }
    }

    checkApiHealth()
    const intervalId = window.setInterval(checkApiHealth, 15000)

    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [])

  useEffect(() => {
    if (!toast) {
      return undefined
    }

    const timeoutId = window.setTimeout(() => setToast(null), toast.tone === 'error' ? 4500 : 2400)
    return () => window.clearTimeout(timeoutId)
  }, [toast])

  useEffect(() => {
    if (!scan || scan.status === 'completed' || scan.status === 'failed') {
      return undefined
    }

    let cancelled = false
    let consecutiveFailures = 0

    const intervalId = window.setInterval(async () => {
      try {
        const nextScan = await getScan(scan.scanId)
        if (!cancelled && nextScan.scanId === scan.scanId) {
          consecutiveFailures = 0
          setScan(nextScan)
        }
      } catch (pollError) {
        if (cancelled) {
          return
        }
        consecutiveFailures += 1
        if (consecutiveFailures >= 4) {
          setScan((prev) =>
            prev && prev.scanId === scan.scanId
              ? { ...prev, status: 'failed', error: pollError.message }
              : prev,
          )
        }
        setError(pollError.message)
      }
    }, 1500)

    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [scan])

  useEffect(() => {
    if (!scan || scan.status !== 'completed' || report) {
      return undefined
    }

    let cancelled = false

    async function loadReport() {
      try {
        const nextReport = await getReport(scan.scanId)
        if (!cancelled) {
          setReport(nextReport)
        }
      } catch (reportError) {
        if (!cancelled) {
          setError(reportError.message)
        }
      }
    }

    loadReport()

    return () => {
      cancelled = true
    }
  }, [report, scan])

  useEffect(() => {
    if (isDemoMode) {
      return undefined
    }

    if (!scan || !report || patchJob || isRequestingPatch) {
      return undefined
    }

    let cancelled = false

    async function loadLatestPatch() {
      try {
        const patches = await getPatches(scan.scanId)
        if (!cancelled && patches.length > 0) {
          setPatchJob(patches[patches.length - 1])
        }
      } catch {}
    }

    loadLatestPatch()

    return () => {
      cancelled = true
    }
  }, [isDemoMode, isRequestingPatch, patchJob, report, scan])

  useEffect(() => {
    if (!patchJob || patchJob.status === 'completed' || patchJob.status === 'failed') {
      return undefined
    }

    let cancelled = false
    let consecutiveFailures = 0

    const intervalId = window.setInterval(async () => {
      try {
        const nextPatch = await getPatch(patchJob.scanId, patchJob.patchId)
        if (!cancelled && nextPatch.patchId === patchJob.patchId) {
          consecutiveFailures = 0
          setPatchJob(nextPatch)
        }
      } catch (pollError) {
        if (cancelled) {
          return
        }
        consecutiveFailures += 1
        if (consecutiveFailures >= 4) {
          setPatchJob((prev) =>
            prev && prev.patchId === patchJob.patchId
              ? { ...prev, status: 'failed', error: pollError.message }
              : prev,
          )
        }
        setPatchError(pollError.message)
      }
    }, 1800)

    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [patchJob])

  useEffect(() => {
    if (!patchJob) {
      return
    }

    if (patchJob.status === 'queued' || patchJob.status === 'running') {
      setPendingPatchTarget({
        findingId: patchJob.findingId,
        evidencePath: patchJob.evidencePath,
      })
      return
    }

    setPendingPatchTarget(null)
  }, [patchJob])

  useEffect(() => {
    if (!scan || !patchJob || patchJob.status !== 'completed' || isDemoMode) {
      return undefined
    }
    // Re-entrancy is tracked in a ref: gating on isVerifyingPatch state would
    // cancel this effect the moment the flag is set, stranding the busy state.
    if (patchVerification?.patchId === patchJob.patchId || verifyingPatchIdRef.current === patchJob.patchId) {
      return undefined
    }

    let cancelled = false
    const targetPatchId = patchJob.patchId
    verifyingPatchIdRef.current = targetPatchId

    async function loadVerificationReceipt() {
      setIsVerifyingPatch(true)
      setVerificationError('')
      try {
        const receipt = await verifyPatch(scan.scanId, targetPatchId)
        if (!cancelled) {
          setPatchVerification(receipt)
        }
      } catch (nextError) {
        if (!cancelled) {
          setVerificationError(nextError.message)
        }
      } finally {
        if (verifyingPatchIdRef.current === targetPatchId) {
          verifyingPatchIdRef.current = null
        }
        setIsVerifyingPatch(false)
      }
    }

    loadVerificationReceipt()

    return () => {
      cancelled = true
    }
  }, [isDemoMode, patchJob, patchVerification, scan])

  async function handleSubmit(event) {
    event.preventDefault()
    setIsDemoMode(false)
    setError('')
    setScan(null)
    setPatchError('')
    setIsRequestingPatch(false)
    setIsRepairingPatch(false)
    setIsVerifyingPatch(false)
    setPendingPatchTarget(null)
    setApplyError('')
    setVerificationError('')
    setExportError('')
    setGitHubReviewError('')
    setPatchJob(null)
    setPatchApply(null)
    setPatchVerification(null)
    setExportBundle(null)
    setGitHubReview(null)
    setReport(null)
    setIsSubmitting(true)

    try {
      const nextScan = await createScan(repoUrl)
      setScan(nextScan)
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  function handleLoadSampleScan() {
    setIsDemoMode(true)
    setRepoUrl(sampleScan.repoUrl)
    setActiveFilter('all')
    setError('')
    setPatchError('')
    setApplyError('')
    setVerificationError('')
    setExportError('')
    setGitHubReviewError('')
    setIsSubmitting(false)
    setIsRequestingPatch(false)
    setIsRepairingPatch(false)
    setIsVerifyingPatch(false)
    setIsApplyingPatch(false)
    setIsRollingBackPatch(false)
    setIsExporting(false)
    setIsGeneratingReview(false)
    setPendingPatchTarget(null)
    setScan(sampleScan)
    setReport(sampleReport)
    setPatchJob(null)
    setPatchApply(null)
    setPatchVerification(null)
    setExportBundle(null)
    setGitHubReview(null)
  }

  function handleChooseDemoRepository(url) {
    setIsDemoMode(false)
    setRepoUrl(url)
    setError('')
  }

  function focusPatchPanel() {
    // Small delay so the focus lands after React commits the new patch state.
    window.setTimeout(() => {
      const panel = patchPanelRef.current
      if (panel) {
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' })
        panel.focus({ preventScroll: true })
      }
    }, 120)
  }

  async function handleGeneratePatch(finding, evidence) {
    if (!scan || isRequestingPatch || isPatchInFlight(patchJob)) {
      return
    }

    if (isDemoMode) {
      const samplePatch = buildSamplePatch(evidence.path, finding.id)
      setPatchError('')
      setApplyError('')
      setVerificationError('')
      setExportError('')
      setGitHubReviewError('')
      setPatchJob(samplePatch)
      setPatchApply(null)
      setPatchVerification(sampleVerification)
      setExportBundle(null)
      setGitHubReview(null)
      focusPatchPanel()
      return
    }

    if (!ollamaReadiness.canGenerate) {
      setPatchError(ollamaReadiness.message)
      return
    }

    setIsRequestingPatch(true)
    setPendingPatchTarget({
      findingId: finding.id,
      evidencePath: evidence.path,
    })
    setPatchError('')
    setPatchJob(null)
    setApplyError('')
    setIsRepairingPatch(false)
    setVerificationError('')
    setExportError('')
    setGitHubReviewError('')
    setPatchApply(null)
    setPatchVerification(null)
    setExportBundle(null)
    setGitHubReview(null)
    focusPatchPanel()
    try {
      const nextPatch = await createPatch(scan.scanId, {
        findingId: finding.id,
        evidencePath: evidence.path,
        model: selectedModel,
      })
      setPatchJob(nextPatch)
    } catch (patchRequestError) {
      setPendingPatchTarget(null)
      setPatchError(patchRequestError.message)
    } finally {
      setIsRequestingPatch(false)
    }
  }

  async function handleApplyPatch() {
    if (!scan || !patchJob || patchJob.status !== 'completed') {
      return
    }

    if (isDemoMode) {
      setApplyError('')
      setPatchApply(buildSampleApplyResult())
      return
    }

    const blockReason = getApplyBlockReason(patchJob, patchApply)
    if (blockReason) {
      setApplyError(blockReason)
      return
    }
    const verificationReason = getVerificationBlockReason(patchJob, patchVerification, 'apply')
    if (verificationReason) {
      setApplyError(verificationReason)
      return
    }

    setIsApplyingPatch(true)
    setApplyError('')
    try {
      const nextApply = await applyPatch(scan.scanId, patchJob.patchId)
      setPatchApply(nextApply)
    } catch (nextError) {
      setApplyError(nextError.message)
    } finally {
      setIsApplyingPatch(false)
    }
  }

  async function handleRepairPatch() {
    if (!scan || !patchJob || patchJob.status !== 'completed') {
      return
    }

    setIsRepairingPatch(true)
    setPatchError('')
    setApplyError('')
    try {
      const repairedPatch = await repairPatch(scan.scanId, patchJob.patchId)
      setPatchJob(repairedPatch)
      setPatchApply(null)
      setPatchVerification(null)
      setExportBundle(null)
      setGitHubReview(null)
      setExportError('')
      setGitHubReviewError('')
    } catch (repairError) {
      setPatchError(repairError.message)
    } finally {
      setIsRepairingPatch(false)
    }
  }

  async function handleVerifyPatch() {
    if (!scan || !patchJob || patchJob.status !== 'completed') {
      return
    }

    if (isDemoMode) {
      setVerificationError('')
      setPatchVerification(sampleVerification)
      return
    }

    setIsVerifyingPatch(true)
    setVerificationError('')
    try {
      const receipt = await verifyPatch(scan.scanId, patchJob.patchId)
      setPatchVerification(receipt)
    } catch (nextError) {
      setVerificationError(nextError.message)
    } finally {
      setIsVerifyingPatch(false)
    }
  }

  async function handleRollbackPatch() {
    if (!patchApply?.applyId) {
      return
    }

    if (isDemoMode) {
      setApplyError('')
      setPatchApply({
        ...patchApply,
        status: 'rolled_back',
        updatedAt: new Date().toISOString(),
        rollbackAvailable: false,
        rollbackReason: 'Sample workspace apply was rolled back in demo mode.',
      })
      return
    }

    setIsRollingBackPatch(true)
    setApplyError('')
    try {
      const nextApply = await rollbackPatchApply(patchApply.applyId)
      setPatchApply(nextApply)
    } catch (nextError) {
      setApplyError(nextError.message)
    } finally {
      setIsRollingBackPatch(false)
    }
  }

  async function handleCreateExport(includePatch) {
    if (!scan || !report) {
      return
    }

    if (isDemoMode) {
      setExportError('')
      setExportBundle({
        ...sampleExportBundle,
        patchId: includePatch && patchJob?.status === 'completed' ? patchJob.patchId : null,
      })
      return
    }

    if (includePatch && exportBlockReason) {
      setExportError(exportBlockReason)
      return
    }

    setIsExporting(true)
    setExportError('')

    try {
      const nextExport = await createExport(scan.scanId, {
        patchId: includePatch && patchJob?.status === 'completed' ? patchJob.patchId : null,
        formats: EXPORT_FORMATS,
      })
      setExportBundle(nextExport)
    } catch (nextError) {
      setExportError(nextError.message)
    } finally {
      setIsExporting(false)
    }
  }

  async function handleCreateGitHubReview() {
    if (!scan || !patchJob || patchJob.status !== 'completed') {
      return
    }

    const reviewBlockReason = getGitHubReviewBlockReason({
      patchJob,
      verification: currentPatchVerification,
      exportBlockReason,
      isDemoMode,
    })
    if (reviewBlockReason) {
      setGitHubReviewError(reviewBlockReason)
      return
    }

    if (isDemoMode) {
      setGitHubReviewError('')
      setGitHubReview(sampleGitHubReview)
      return
    }

    setIsGeneratingReview(true)
    setGitHubReviewError('')

    try {
      const nextReview = await createGitHubReview(scan.scanId, {
        patchId: patchJob.patchId,
        pullRequestNumber: githubPrNumber ? Number(githubPrNumber) : null,
        postComment: shouldPostReview && Boolean(githubPrNumber) && Boolean(currentPatchVerification?.exportReady),
      })
      setGitHubReview(nextReview)
    } catch (nextError) {
      setGitHubReviewError(nextError.message)
    } finally {
      setIsGeneratingReview(false)
    }
  }

  function handleDownload(file) {
    if (!file.downloadPath) {
      setExportError('Sample files are illustrative. Run a live export to download real report artifacts.')
      return
    }
    window.open(getApiUrl(file.downloadPath), '_blank', 'noopener,noreferrer')
  }

  async function handleCopyReview() {
    if (!githubReview?.commentBody) {
      return
    }
    try {
      await navigator.clipboard.writeText(githubReview.commentBody)
      setToast({ message: 'GitHub review comment copied to clipboard.', tone: 'success' })
    } catch {
      setToast({ message: 'Could not copy the review comment — check browser clipboard permissions.', tone: 'error' })
    }
  }

  async function handleCopyDiff() {
    if (!patchJob?.diff) {
      return
    }
    try {
      await navigator.clipboard.writeText(patchJob.diff)
      setToast({ message: 'Patch diff copied to clipboard.', tone: 'success' })
    } catch {
      setToast({ message: 'Could not copy diff — check browser clipboard permissions.', tone: 'error' })
    }
  }

  async function handleRefreshOllama() {
    setIsRefreshingOllama(true)
    try {
      const nextStatus = await getOllamaStatus(selectedModel)
      applyOllamaState(nextStatus)
    } catch (nextError) {
      const fallbackModelName = selectedModel || FALLBACK_MODEL
      const fallbackStatus = buildFallbackOllamaStatus(selectedModel, nextError.message)
      setOllamaStatus(fallbackStatus)
      setOllamaError(nextError.message)
      setModels([{ name: fallbackModelName }])
      setSelectedModel(fallbackModelName)
    } finally {
      setIsRefreshingOllama(false)
    }
  }

  async function handleWarmSelectedModel() {
    if (!selectedModel) {
      return
    }

    setIsWarmingModel(true)
    setOllamaError('')
    try {
      const nextStatus = await warmOllamaModel(selectedModel)
      applyOllamaState(nextStatus)
    } catch (nextError) {
      const fallbackModelName = selectedModel || FALLBACK_MODEL
      const fallbackStatus = buildFallbackOllamaStatus(selectedModel, nextError.message)
      setOllamaStatus(fallbackStatus)
      setOllamaError(nextError.message)
      setModels([{ name: fallbackModelName }])
      setSelectedModel(fallbackModelName)
    } finally {
      setIsWarmingModel(false)
    }
  }

  const readinessScore = report?.summary.portabilityScore ?? '--'
  const filteredFindings =
    report?.findings.filter((finding) => activeFilter === 'all' || finding.severity === activeFilter) ?? []
  const severityCounts = countBySeverity(report?.findings ?? [])
  const activeFinding = findActiveFinding(report, patchJob)
  const isPatchBusy = isRequestingPatch || isPatchInFlight(patchJob)
  const ollamaReadiness = useMemo(() => deriveOllamaReadiness(ollamaStatus, selectedModel), [ollamaStatus, selectedModel])
  const latestPatchReady = patchJob?.status === 'completed'
  const currentPatchVerification = patchVerification?.patchId === patchJob?.patchId ? patchVerification : null
  const hasActiveWorkspaceApply = patchApply?.status === 'applied'
  const applyLockedByDifferentPatch = hasActiveWorkspaceApply && patchApply.patchId !== patchJob?.patchId
  const applyBlockReason = getApplyBlockReason(patchJob, patchApply)
  const verificationBlockReason = getVerificationBlockReason(patchJob, currentPatchVerification, 'apply')
  const exportBlockReason = getVerificationBlockReason(patchJob, currentPatchVerification, 'export')
  const canApplyCurrentPatch =
    !isDemoMode && latestPatchReady && !hasActiveWorkspaceApply && !applyBlockReason && !verificationBlockReason
  const canRepairCurrentPatch = latestPatchReady && hasResponseArtifactLeak(patchJob) && !isRepairingPatch
  const canVerifyCurrentPatch = latestPatchReady && !isVerifyingPatch && !isRepairingPatch && !isApplyingPatch
  const canExportCurrentPatch = latestPatchReady && !isExporting && !exportBlockReason
  const githubReviewBlockReason = getGitHubReviewBlockReason({
    patchJob,
    verification: currentPatchVerification,
    exportBlockReason,
    isDemoMode,
  })
  const canBuildGitHubReview = latestPatchReady && !isGeneratingReview && !githubReviewBlockReason
  const canPostGitHubReview = canBuildGitHubReview && !isDemoMode
  const exportFiles = useMemo(() => prioritizeExportFiles(exportBundle?.files ?? []), [exportBundle])
  const workspaceClassName = report ? 'workspace workspace-has-report' : 'workspace'
  const canGeneratePatch = Boolean(scan) && !isPatchBusy && (isDemoMode || ollamaReadiness.canGenerate)
  const patchStatusCopy = buildPatchStatusCopy(patchJob, pendingPatchTarget, selectedModel, ollamaReadiness)
  const decisionSummary = buildPatchDecisionSummary({
    patchJob,
    verification: currentPatchVerification,
    applyBlockReason,
    exportBlockReason,
    isDemoMode,
  })
  const ollamaFacts = buildOllamaFacts(ollamaStatus)
  const executiveSummary = buildExecutiveSummary(report)
  const scoreTone = scoreToneClass(report?.summary.portabilityScore)
  const scanInProgress = scan && scan.status !== 'completed' && scan.status !== 'failed'
  const scanFailed = scan?.status === 'failed'

  return (
    <div className="app-shell">
      <div className="ambient-bg" aria-hidden="true"></div>
      <div className="ambient-grid" aria-hidden="true"></div>
      {toast ? (
        <div className={`toast-banner${toast.tone === 'error' ? ' error' : ''}`} role="status" aria-live="polite">
          <span>{toast.message}</span>
          <button type="button" className="toast-dismiss" aria-label="Dismiss notification" onClick={() => setToast(null)}>
            ×
          </button>
        </div>
      ) : null}

      <header className="topbar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M7.5 2.5h14v14l-4-4v-6h-6l-4-4Z" fill="#fff" />
              <path d="M2.5 21.5v-9.6l4.4-4.4v9.6h9.6l-4.4 4.4H2.5Z" fill="#fff" fillOpacity="0.82" />
            </svg>
          </div>
          <div>
            <p className="eyeline">ROCmPorter Product Build</p>
            <h1>ROCmPorter Agent</h1>
            <p className="brand-tagline">CUDA-to-ROCm readiness scans, reviewable patch artifacts, and audit-grade exports — fully local.</p>
          </div>
        </div>
        <div className="topbar-actions">
          <SystemStatusChips apiHealth={apiHealth} ollamaStatus={ollamaStatus} />
          <div className="topbar-chip">Scan: {humanizeStatus(scan?.status ?? 'idle')}</div>
          <a className="topbar-pricing-link" href="#pricing">View pricing →</a>
        </div>
      </header>

      <BenchmarkProofPanel proof={benchmarkProof} />

      <main id="workspace" className={workspaceClassName}>
        <aside className="control-panel">
          <section className="panel-card hero-panel">
            <p className="section-label">Repository Intake</p>
            <h2>Scan a GitHub repo and generate single-file ROCm review artifacts.</h2>
            <p className="panel-copy">
              The scan stays evidence-driven, the patch flow stays reviewable, and the export bundle stays auditable.
            </p>

            <ol className="flow-steps">
              <li>Scan a repository for CUDA/NVIDIA assumptions.</li>
              <li>Choose one evidence file and generate a full or conservative partial patch artifact.</li>
              <li>Verify, export, and create a GitHub-ready review artifact.</li>
            </ol>

            <form className="repo-form" onSubmit={handleSubmit}>
              <label htmlFor="repo-url">Public GitHub repository URL</label>
              <input
                id="repo-url"
                name="repoUrl"
                type="url"
                value={repoUrl}
                onChange={(event) => setRepoUrl(event.target.value)}
                placeholder="https://github.com/org/repo"
                autoComplete="off"
              />
              <button className="primary-button" type="submit" disabled={isSubmitting}>
                {isSubmitting ? 'Starting Scan...' : 'Analyze Repository'}
              </button>
              <button className="secondary-button full-width-button" type="button" onClick={handleLoadSampleScan}>
                Load Sample Scan
              </button>
            </form>

            <div className="demo-repo-list">
              <span className="metric-label">Known Demo Repos</span>
              {demoRepositories.map((repo) => (
                <button
                  key={repo.url}
                  type="button"
                  className="repo-chip"
                  title={repo.note}
                  aria-label={`Use ${repo.name}: ${repo.note}`}
                  onClick={() => handleChooseDemoRepository(repo.url)}
                >
                  {repo.name}
                </button>
              ))}
            </div>

            {isDemoMode ? (
              <div className="warning-banner low">
                <strong>sample demo mode</strong>
                <span>
                  Loaded a realistic extension-cpp scan so the pitch flow works even when internet, GitHub, or Ollama is slow.
                </span>
              </div>
            ) : null}

            {error ? <p className="error-banner">{error}</p> : null}
          </section>

          <section className="panel-card">
            <div className="section-head compact-head">
              <div>
                <p className="section-label">Patch Model</p>
                <h3>{ollamaStatus?.version?.includes('hosted') ? 'Hosted AI model' : 'AI patch model'}</h3>
              </div>
              <span className="support-chip">single-file</span>
            </div>
            <label className="select-label" htmlFor="model-select">
              Installed local coding models
            </label>
            <select
              id="model-select"
              className="model-select"
              value={selectedModel}
              onChange={(event) => setSelectedModel(event.target.value)}
            >
              {models.map((model) => (
                <option key={model.name} value={model.name}>
                  {model.name}
                </option>
              ))}
            </select>
            <div className={`warning-banner ${ollamaReadiness.severity}`}>
              <div className="readiness-head">
                <strong>model readiness</strong>
                <span className={`readiness-pill ${ollamaReadiness.kind}`}>{ollamaReadiness.label}</span>
              </div>
              <span>{ollamaReadiness.message}</span>
            </div>
            <p className="status-hint">{formatOllamaMeta(ollamaStatus)}</p>
            {ollamaFacts.length ? (
              <div className="ollama-fact-grid">
                {ollamaFacts.map((fact) => (
                  <div key={fact.label} className="ollama-fact-card">
                    <span className="metric-label">{fact.label}</span>
                    <strong>{fact.value}</strong>
                  </div>
                ))}
              </div>
            ) : null}
            <div className="local-first-fact-row" aria-label="Local-first operating facts">
              {localFirstFacts.map((fact) => (
                <span key={fact} className="local-first-fact-chip">
                  {fact}
                </span>
              ))}
            </div>
            {ollamaError ? <p className="error-banner">{ollamaError}</p> : null}
            <div className="compact-button-row">
              <button
                type="button"
                className="secondary-button"
                disabled={isRefreshingOllama}
                onClick={handleRefreshOllama}
              >
                {isRefreshingOllama ? 'Refreshing...' : 'Refresh Status'}
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={!ollamaReadiness.canWarm || isWarmingModel}
                title={!ollamaReadiness.canWarm && !isWarmingModel ? ollamaReadiness.message : undefined}
                onClick={handleWarmSelectedModel}
              >
                {isWarmingModel ? 'Warming Model...' : 'Warm Selected Model'}
              </button>
            </div>
          </section>

          <section className="panel-card status-card">
            <div>
              <p className="section-label">Scan Progress</p>
              <h3>{humanizeStatus(scan?.progress.stage ?? 'waiting')}</h3>
            </div>
            <div className="progress-track" aria-hidden="true">
              <div
                className={`progress-bar${scanInProgress ? ' progress-bar-active' : ''}${scanFailed ? ' progress-bar-failed' : ''}`}
                style={{ width: `${scanFailed ? 100 : (scan?.progress.percent ?? 0)}%` }}
              ></div>
            </div>
            <p className="status-copy">
              {scanFailed
                ? `Scan failed for ${trimRepoUrl(scan.repoUrl)}. ${scan.error ?? 'Check the URL and try again.'}`
                : scan
                  ? `${scan.progress.percent}% complete for ${trimRepoUrl(scan.repoUrl)}`
                  : 'Start with one public repository and we will generate a migration report plus patch-ready evidence.'}
            </p>
          </section>
        </aside>

        <section className="report-panel">
          <div className="report-header">
            <div>
              <p className="section-label">ROCm Readiness</p>
              {scanInProgress ? (
                <h2 className="loading-inline">
                  <span className="spinner" aria-hidden="true"></span>
                  Scanning {trimRepoUrl(scan.repoUrl)}… {scan.progress.percent}%
                </h2>
              ) : (
                <h2>{report ? report.repo.name : scanFailed ? 'Scan failed' : 'Ready when you are'}</h2>
              )}
            </div>
            <div className="header-actions">
              {report ? (
                <>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={isExporting}
                    onClick={() => handleCreateExport(false)}
                  >
                    {isExporting ? 'Building Bundle...' : 'Export Report'}
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={!canExportCurrentPatch}
                    title={exportBlockReason || undefined}
                    onClick={() => handleCreateExport(true)}
                  >
                    Export With Patch
                  </button>
                </>
              ) : null}
              <div
                className={`score-orb ${scoreTone}${report ? '' : ' score-empty'}`}
                style={{ '--score': typeof readinessScore === 'number' ? readinessScore : 0 }}
                role={report ? 'img' : undefined}
                aria-hidden={report ? undefined : true}
                aria-label={report ? `ROCm portability score ${readinessScore} out of 100` : undefined}
              >
                <span>{readinessScore}</span>
                <small className="score-orb-caption">/ 100</small>
              </div>
            </div>
          </div>

          {scanFailed ? (
            <section className="panel-card scan-failed-card">
              <div className="error-banner">
                <strong>Scan failed.</strong>{' '}
                {scan.error || error || 'The repository could not be cloned or scanned. Check the URL and try again.'}
              </div>
              <p className="status-copy">
                Double-check that the repository URL is public and reachable, then analyze it again — or load the
                sample scan to keep exploring the product.
              </p>
              <div className="zero-state-cta">
                <button type="button" className="primary-button" onClick={handleSubmit}>
                  Try Again
                </button>
                <button type="button" className="secondary-button" onClick={handleLoadSampleScan}>
                  Load Sample Scan
                </button>
              </div>
            </section>
          ) : null}

          {scanInProgress && !report ? (
            <section className="panel-card" aria-label="Scan in progress">
              <p className="section-label">Analyzing Repository</p>
              <h3>
                {humanizeStatus(scan.progress.stage)} — {scan.progress.percent}%
              </h3>
              <p className="status-copy">
                Cloning the repository and scanning for CUDA and NVIDIA-specific assumptions. This usually takes a few
                seconds on public repos.
              </p>
              <div className="skeleton-block" style={{ padding: '18px' }} aria-hidden="true">
                <div className="skeleton-line long"></div>
                <div className="skeleton-line medium"></div>
                <div className="skeleton-line long"></div>
                <div className="skeleton-line short"></div>
              </div>
            </section>
          ) : null}

          {!report && !scanInProgress && !scanFailed ? (
            <section className="panel-card zero-state-hero">
              <p className="section-label">ROCm Readiness Report</p>
              <h3>Scan any CUDA repository. Get an evidence-backed migration report.</h3>
              <p>
                The report lands here with a portability score, file-level findings, reviewable ROCm patch artifacts,
                and audit-grade export bundles.
              </p>
              <div className="zero-state-steps">
                <div className="zero-state-step">
                  <strong>1</strong>
                  <span>Scan a repository for CUDA and NVIDIA-specific assumptions.</span>
                </div>
                <div className="zero-state-step">
                  <strong>2</strong>
                  <span>Generate a reviewable single-file ROCm patch from any evidence file.</span>
                </div>
                <div className="zero-state-step">
                  <strong>3</strong>
                  <span>Verify, export, and build a GitHub-ready review artifact.</span>
                </div>
              </div>
              <div className="zero-state-cta">
                <button type="button" className="primary-button" onClick={handleLoadSampleScan}>
                  Load Sample Scan
                </button>
              </div>
            </section>
          ) : null}

          {report ? (
            <section className="panel-card executive-summary-card">
              <div className="section-head compact-head">
                <div>
                  <p className="section-label">Executive Summary</p>
                  <h3>ROCm migration readiness at a glance</h3>
                </div>
                <span className="support-chip">deterministic</span>
              </div>
              <p className="executive-summary-text">{executiveSummary}</p>
              <SeverityBreakdown findings={report.findings} />
            </section>
          ) : null}

          {report ? (
            <div className="summary-grid">
              <article className="metric-card">
                <span className="metric-label">Risk Level</span>
                <strong>{report.summary.riskLevel}</strong>
              </article>
              <article className="metric-card">
                <span className="metric-label">Estimated Effort</span>
                <strong>{report.summary.estimatedEffort}</strong>
              </article>
              <article className="metric-card">
                <span className="metric-label">Languages</span>
                <strong>{report.build.languages.join(', ')}</strong>
              </article>
              <article className="metric-card">
                <span className="metric-label">Build Systems</span>
                <strong>{report.build.buildSystems.join(', ')}</strong>
              </article>
              {report.coverage ? (
                <>
                  <article className="metric-card">
                    <span className="metric-label">Files Scanned</span>
                    <strong>
                      {report.coverage.scannedFiles}/{report.coverage.totalFiles}
                    </strong>
                  </article>
                  <article className="metric-card">
                    <span className="metric-label">Ruleset</span>
                    <strong>{report.rulesetVersion ?? 'n/a'}</strong>
                  </article>
                </>
              ) : null}
            </div>
          ) : null}

          {report ? (
          <div className="report-grid">
            <section className="panel-card findings-card">
              <div className="section-head">
                <div>
                  <p className="section-label">Compatibility Findings</p>
                  <h3>Evidence-backed blockers and patch entry points</h3>
                </div>
                <div className="filter-row" role="group" aria-label="Filter findings by severity">
                  {['all', 'critical', 'high', 'medium', 'low'].map((severity) => (
                    <button
                      key={severity}
                      type="button"
                      className={activeFilter === severity ? 'filter-chip active' : 'filter-chip'}
                      aria-pressed={activeFilter === severity}
                      onClick={() => setActiveFilter(severity)}
                    >
                      {severity}
                      {severity === 'all' ? ` (${report?.findings.length ?? 0})` : ` (${severityCounts[severity] ?? 0})`}
                    </button>
                  ))}
                </div>
              </div>

              {report ? (
                <div className="finding-list">
                  {filteredFindings.map((finding) => (
                    <article key={finding.id} className={`finding-item ${finding.severity}`}>
                      <div className="finding-topline">
                        <span className={`severity-badge ${finding.severity}`}>{finding.severity}</span>
                        <span className="confidence-pill">{finding.confidence} confidence</span>
                      </div>
                      <h4>{finding.title}</h4>
                      <p>{finding.details}</p>
                      <p className="recommendation">{finding.recommendation}</p>

                      <div className="evidence-stack">
                        {finding.evidence.map((entry) => (
                          <div
                            key={`${finding.id}-${entry.path}-${entry.lineStart ?? 'path'}-${entry.lineEnd ?? ''}`}
                            className="evidence-card"
                          >
                            <div className="evidence-head">
                              <div>
                                <strong>{entry.path}</strong>
                                <span className="line-meta">{formatLineRange(entry)}</span>
                              </div>
                              <button
                                type="button"
                                className="secondary-button"
                                disabled={!canGeneratePatch}
                                onClick={() => handleGeneratePatch(finding, entry)}
                              >
                                {patchActionLabel(patchJob, pendingPatchTarget, finding.id, entry.path, isRequestingPatch)}
                              </button>
                            </div>
                            {entry.matchText ? <p className="match-text">Match: {entry.matchText}</p> : null}
                            {entry.snippet ? <pre className="snippet-block">{entry.snippet}</pre> : null}
                          </div>
                        ))}
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <EmptyState text="The first report will appear here with file-level evidence, line windows, and patch generation actions." />
              )}
            </section>

            <section className="panel-card patch-panel" ref={patchPanelRef} tabIndex={-1}>
              <p className="section-label">Patch Workspace</p>
              <h3>{activeFinding ? activeFinding.title : 'Generate a patch from any evidence file'}</h3>
              <p className="status-copy">{patchStatusCopy}</p>

              {decisionSummary ? (
                <div className={`decision-strip ${decisionSummary.severity}`}>
                  <div className="decision-copy">
                    <span className="metric-label">{decisionSummary.label}</span>
                    <strong>{decisionSummary.title}</strong>
                    <p>{decisionSummary.message}</p>
                  </div>
                  <div className="decision-pill-row">
                    <span className={`decision-pill ${decisionSummary.applyReady ? 'ready' : 'blocked'}`}>
                      Apply {decisionSummary.applyReady ? 'ready' : 'blocked'}
                    </span>
                    <span className={`decision-pill ${decisionSummary.exportReady ? 'ready' : 'blocked'}`}>
                      Export {decisionSummary.exportReady ? 'ready' : 'blocked'}
                    </span>
                  </div>
                </div>
              ) : null}

              {patchError ? <p className="error-banner">{patchError}</p> : null}
              {applyError ? <p className="error-banner">{applyError}</p> : null}
              {verificationError ? <p className="error-banner">{verificationError}</p> : null}
              {!patchJob && ollamaReadiness.kind !== 'ready' ? (
                <div className={`warning-banner ${ollamaReadiness.severity}`}>
                  <strong>{ollamaReadiness.label.toLowerCase()}</strong>
                  <span>{ollamaReadiness.message}</span>
                </div>
              ) : null}

              {patchJob ? (
                <div className="patch-result">
                  {isDemoMode ? (
                    <SamplePreviewNote text="Sample preview only. Patch paths and receipts are realistic, but workspace apply stays disabled until you run a live repository flow." />
                  ) : null}
                  {isPatchBusy ? (
                    <div className="warning-banner low">
                      <strong>local patch generation</strong>
                      <span>
                        Ollama is generating a single-file patch locally. On slower machines this can take a while; if it exceeds the
                        backend timeout, it will fail cleanly instead of appearing stuck forever.
                      </span>
                    </div>
                  ) : null}

                  <div className="patch-meta-grid">
                    <div className="metric-card tight-card">
                      <span className="metric-label">Patch Status</span>
                      <strong>{humanizeStatus(patchJob.status)}</strong>
                    </div>
                    <div className="metric-card tight-card">
                      <span className="metric-label">Target File</span>
                      <strong>{patchJob.evidencePath}</strong>
                    </div>
                  </div>

                  {patchJob.riskAssessment ? (
                    <div className="risk-card">
                      <div className="risk-head">
                        <div>
                          <span className="metric-label">Review Risk</span>
                          <h4>
                            {patchJob.riskAssessment.score}/100
                            <span className={`risk-pill ${patchJob.riskAssessment.level}`}>
                              {patchJob.riskAssessment.level}
                            </span>
                          </h4>
                        </div>
                      </div>
                      <p>{patchJob.riskAssessment.summary}</p>
                      {patchJob.riskAssessment.reasons?.length ? (
                        <ul className="inline-list">
                          {patchJob.riskAssessment.reasons.map((reason) => (
                            <li key={reason}>{reason}</li>
                          ))}
                        </ul>
                      ) : null}
                      {patchJob.riskAssessment.checklist?.length ? (
                        <div className="checklist-block">
                          <span className="metric-label">Approval Checklist</span>
                          <ul className="inline-list">
                            {patchJob.riskAssessment.checklist.map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  {patchJob.validation ? (
                    <div className="patch-copy-block">
                      <span className="metric-label">Syntax Validation</span>
                      <p>
                        {patchJob.validation.state} via {patchJob.validation.tool}
                      </p>
                      <p>{patchJob.validation.summary}</p>
                      {patchJob.validation.details?.length ? (
                        <ul className="inline-list">
                          {patchJob.validation.details.map((detail) => (
                            <li key={detail}>{detail}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ) : null}

                  {patchJob.warnings?.length ? (
                    <div className="warning-stack">
                      {patchJob.warnings.map((warning) => (
                        <div key={warning.code} className={`warning-banner ${warning.severity}`}>
                          <strong>{warningTitle(warning)}</strong>
                          <span>{warning.message}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}

                  {Boolean(patchJob.changedLineCount || patchJob.changedHunkCount) && (
                    <div className="patch-meta-grid">
                      <div className="metric-card tight-card">
                        <span className="metric-label">Changed Lines</span>
                        <strong>{patchJob.changedLineCount ?? 'n/a'}</strong>
                      </div>
                      <div className="metric-card tight-card">
                        <span className="metric-label">Changed Hunks</span>
                        <strong>{patchJob.changedHunkCount ?? 'n/a'}</strong>
                      </div>
                    </div>
                  )}

                  {patchJob.rationale ? (
                    <div className="patch-copy-block">
                      <span className="metric-label">Rationale</span>
                      <p>{patchJob.rationale}</p>
                    </div>
                  ) : null}

                  {patchJob.savedPatchPath ? (
                    <div className="patch-copy-block">
                      <span className="metric-label">Saved Patch File</span>
                      <p className="path-copy">{patchJob.savedPatchPath}</p>
                    </div>
                  ) : null}

                  {patchJob.savedPatchedFilePath ? (
                    <div className="patch-copy-block">
                      <span className="metric-label">Patched File Snapshot</span>
                      <p className="path-copy">{patchJob.savedPatchedFilePath}</p>
                    </div>
                  ) : null}

                  {patchJob.sourceFilePath ? (
                    <div className="patch-copy-block">
                      <span className="metric-label">Source File</span>
                      <p className="path-copy">{patchJob.sourceFilePath}</p>
                    </div>
                  ) : null}

                  {latestPatchReady ? (
                    <div className="workspace-action-card">
                      <div
                        className={`warning-banner ${
                          patchJob.validation?.state === 'failed' || patchJob.riskAssessment?.level === 'high' ? 'high' : 'medium'
                        }`}
                      >
                        <strong>workspace write</strong>
                        <span>
                          Apply writes this patched file into the scanned workspace copy first. Review the diff, warnings, and validation
                          before moving any change further.
                        </span>
                      </div>

                      <div className="github-button-row">
                        {hasResponseArtifactLeak(patchJob) ? (
                          <button
                            type="button"
                            className="secondary-button"
                            disabled={!canRepairCurrentPatch}
                            onClick={handleRepairPatch}
                          >
                            {isRepairingPatch ? 'Repairing Patch...' : 'Repair Artifacts'}
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={!canVerifyCurrentPatch}
                          onClick={handleVerifyPatch}
                        >
                          {isVerifyingPatch ? 'Verifying Patch...' : 'Verify Patch'}
                        </button>
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={!canApplyCurrentPatch || isApplyingPatch}
                          title={applyBlockReason || verificationBlockReason || undefined}
                          onClick={handleApplyPatch}
                        >
                          {isApplyingPatch ? 'Applying Patch...' : 'Apply In Workspace'}
                        </button>
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={!patchApply?.applyId || patchApply.status !== 'applied' || isRollingBackPatch}
                          onClick={handleRollbackPatch}
                        >
                          {isRollingBackPatch ? 'Rolling Back...' : 'Rollback Last Apply'}
                        </button>
                      </div>

                      {applyLockedByDifferentPatch ? (
                        <p className="status-hint">
                          Roll back the current workspace apply before writing a different patch into the scanned repo copy.
                        </p>
                      ) : isDemoMode ? (
                        <p className="status-hint">Sample preview does not write into the scanned workspace. Run a live scan to enable apply.</p>
                      ) : applyBlockReason ? (
                        <p className="status-hint">{applyBlockReason}</p>
                      ) : verificationBlockReason ? (
                        <p className="status-hint">{verificationBlockReason}</p>
                      ) : null}
                    </div>
                  ) : null}

                  {patchVerification ? (
                    <div className="patch-copy-block">
                      <div className={`warning-banner ${verificationSeverity(patchVerification)}`}>
                        <strong>{verificationLabel(patchVerification)}</strong>
                        <span>{patchVerification.summary}</span>
                      </div>
                      <div className="patch-meta-grid">
                        <div>
                          <span className="metric-label">Receipt</span>
                          <strong>{patchVerification.receiptId}</strong>
                        </div>
                        <div>
                          <span className="metric-label">Patch</span>
                          <strong>{patchVerification.patchId}</strong>
                        </div>
                        <div>
                          <span className="metric-label">Apply Ready</span>
                          <strong>{patchVerification.applyReady ? 'yes' : 'no'}</strong>
                        </div>
                        <div>
                          <span className="metric-label">Export Ready</span>
                          <strong>{patchVerification.exportReady ? 'yes' : 'no'}</strong>
                        </div>
                      </div>
                      <p className="path-copy">Generated: {formatTimestamp(patchVerification.generatedAt)}</p>
                      {patchVerification.savedReceiptPath ? (
                        <p className="path-copy">Receipt: {patchVerification.savedReceiptPath}</p>
                      ) : null}
                      {patchVerification.artifactHashes ? (
                        <div className="hash-list">
                          <span className="metric-label">Artifact Hashes</span>
                          {Object.entries(patchVerification.artifactHashes).map(([key, value]) => (
                            <p key={key} className="path-copy">
                              {key}: {value}
                            </p>
                          ))}
                        </div>
                      ) : null}
                      <ul className="inline-list">
                        {patchVerification.checks.map((check) => (
                          <li key={check.code}>
                            <strong>{check.state}</strong> {check.label}: {check.message}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {patchApply ? (
                    <div className="patch-copy-block">
                      <span className="metric-label">Latest Workspace Action</span>
                      <div className="patch-meta-grid">
                        <div>
                          <strong>{humanizeStatus(patchApply.status)}</strong>
                          <span className="path-copy">{patchApply.applyId}</span>
                        </div>
                        <div>
                          <strong>{patchApply.patchId}</strong>
                          <span className="path-copy">patch artifact</span>
                        </div>
                      </div>
                      <p className="path-copy">Target: {patchApply.targetFilePath}</p>
                      <p className="path-copy">Backup: {patchApply.backupFilePath}</p>
                      <p className="path-copy">Applied snapshot: {patchApply.appliedFilePath}</p>
                    </div>
                  ) : null}

                  {patchJob.error ? (
                    <div className="patch-copy-block">
                      <span className="metric-label">Patch Error</span>
                      <p>{patchJob.error}</p>
                    </div>
                  ) : null}

                  {patchJob.diff ? (
                    <div className="diff-block">
                      <div className="section-head compact-head">
                        <div>
                          <p className="section-label">Unified Diff</p>
                          <h4>{patchJob.evidencePath}</h4>
                        </div>
                        <button type="button" className="secondary-button" onClick={handleCopyDiff}>
                          Copy Diff
                        </button>
                      </div>
                      <DiffView text={patchJob.diff} />
                    </div>
                  ) : null}
                </div>
              ) : (
                <EmptyState text="The patch result panel will show rationale, validation, warnings, saved patch path, and a unified diff preview here." />
              )}
            </section>

            <section className="panel-card github-panel">
              <p className="section-label">GitHub Review</p>
              <h3>Export-gated review artifact</h3>
              <p className="status-copy">
                {githubReview
                  ? `Review artifact ready for ${githubReview.repository}`
                  : githubReviewBlockReason ||
                    'Generate a copy-ready GitHub review comment from an export-ready patch.'}
              </p>
              {isDemoMode ? (
                <SamplePreviewNote text="Sample preview labels this review as a workflow artifact. Use a live patch run before posting or copying anything into a real pull request." />
              ) : null}

              <div className="github-controls">
                <label className="select-label" htmlFor="pr-number">
                  Pull request number
                </label>
                <input
                  id="pr-number"
                  className="model-select"
                  type="number"
                  min="1"
                  value={githubPrNumber}
                  onChange={(event) => setGitHubPrNumber(event.target.value)}
                  placeholder="Optional unless posting"
                />
                <label className="toggle-row">
                  <input
                    type="checkbox"
                    checked={shouldPostReview}
                    disabled={!canPostGitHubReview}
                    onChange={(event) => setShouldPostReview(event.target.checked)}
                  />
                  <span>Post only after export-ready verification and backend token setup</span>
                </label>
                <div className="github-button-row">
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={!canBuildGitHubReview}
                    onClick={handleCreateGitHubReview}
                  >
                    {isGeneratingReview ? 'Building Review...' : 'Build GitHub Review'}
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={!githubReview?.commentBody}
                    onClick={handleCopyReview}
                  >
                    Copy Comment
                  </button>
                </div>
              </div>

              {githubReviewBlockReason ? <p className="status-hint">{githubReviewBlockReason}</p> : null}
              {githubReviewError ? <p className="error-banner">{githubReviewError}</p> : null}

              {githubReview ? (
                <div className="github-review-result">
                  <div className="patch-meta-grid">
                    <div className="metric-card tight-card">
                      <span className="metric-label">Risk</span>
                      <strong>
                        {githubReview.riskScore}/100 ({githubReview.riskLevel})
                      </strong>
                    </div>
                    <div className="metric-card tight-card">
                      <span className="metric-label">Repository</span>
                      <strong>{githubReview.repository}</strong>
                    </div>
                    <div className="metric-card tight-card">
                      <span className="metric-label">Export Ready</span>
                      <strong>{githubReview.exportReady ? 'yes' : 'no'}</strong>
                    </div>
                    <div className="metric-card tight-card">
                      <span className="metric-label">Apply Ready</span>
                      <strong>{githubReview.applyReady ? 'yes' : 'no'}</strong>
                    </div>
                  </div>

                  <div className="patch-copy-block">
                    <span className="metric-label">Review Summary</span>
                    <p>{githubReview.summary}</p>
                    {githubReview.posted && githubReview.postUrl ? (
                      <p className="path-copy">{githubReview.postUrl}</p>
                    ) : null}
                    {githubReview.postError ? <p>{githubReview.postError}</p> : null}
                  </div>

                  <div className="patch-copy-block">
                    <span className="metric-label">Saved Review Files</span>
                    <p className="path-copy">{githubReview.savedMarkdownPath}</p>
                    <p className="path-copy">{githubReview.savedJsonPath}</p>
                    <p className="path-copy">{githubReview.savedInlineCommentsPath}</p>
                    <p>{githubReview.inlineCommentsCount} inline review suggestions prepared.</p>
                    {githubReview.savedPrSafeInlineCommentsPath ? (
                      <>
                        <p className="path-copy">{githubReview.savedPrSafeInlineCommentsPath}</p>
                        <p>{githubReview.prSafeInlineCommentsCount} PR-safe inline comments remained after diff filtering.</p>
                      </>
                    ) : null}
                  </div>

                  <div className="diff-block">
                    <div className="section-head compact-head">
                      <div>
                        <p className="section-label">Comment Preview</p>
                        <h4>Verified review summary and suggested patch text</h4>
                      </div>
                    </div>
                    <pre className="diff-code">{githubReview.commentBody}</pre>
                  </div>
                </div>
              ) : (
                <EmptyState text="The review panel will render a GitHub-ready PR comment, saved review files, and optional post status once generated." />
              )}
            </section>

            <section className="panel-card export-panel">
              <p className="section-label">Export Bundle</p>
              <h3>Offline report, diff artifacts, and audit files</h3>
              <p className="status-copy">
                {exportBundle
                  ? `Bundle ready at ${exportBundle.rootPath}`
                  : 'Build a bundle after the scan. Add the patch artifact when you want report plus diff together.'}
              </p>
              {isDemoMode ? (
                <SamplePreviewNote text="Sample preview bundle entries are illustrative. Run the same flow on a live repository when you need downloadable artifacts." />
              ) : null}

              {exportError ? <p className="error-banner">{exportError}</p> : null}
              {exportBlockReason ? <p className="status-hint">{exportBlockReason}</p> : null}
              {exportBundle && patchJob?.patchMode === 'partial' && currentPatchVerification?.exportReady && !currentPatchVerification?.applyReady ? (
                <p className="status-hint">Export-ready review bundle; workspace apply is still blocked.</p>
              ) : null}

              {exportBundle?.warnings?.length ? (
                <div className="patch-copy-block">
                  <span className="metric-label">Export Notes</span>
                  <ul className="inline-list">
                    {exportBundle.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {exportFiles.length ? (
                <div className="export-file-list">
                  {exportFiles.map((file) => (
                    <div key={`${file.kind}-${file.path}`} className="export-file-card">
                      <div>
                        <strong>{file.label}</strong>
                        <span className="path-copy">{file.path}</span>
                      </div>
                      <button
                        type="button"
                        className="secondary-button"
                        disabled={isDemoMode}
                        onClick={() => handleDownload(file)}
                      >
                        {isDemoMode ? 'Preview Only' : 'Download'}
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState text="The bundle panel will list report.json, summary.md, HTML report, patch diffs, and the zip package once generated." />
              )}
            </section>

            <section className="panel-card">
              <p className="section-label">Migration Checklist</p>
              <h3>Execution path after the first scan</h3>
              {report ? (
                <ol className="checklist">
                  {report.nextSteps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
              ) : (
                <EmptyState text="Once the scan finishes, this panel becomes the migration checklist for the repo." />
              )}
            </section>

            <section className="panel-card">
              <p className="section-label">GPU Signals</p>
              <h3>Files worth reviewing first</h3>
              {report ? (
                <ul className="signal-list">
                  {report.build.gpuSignals.map((signal) => (
                    <li key={signal}>{signal}</li>
                  ))}
                </ul>
              ) : (
                <EmptyState text="We surface the highest-value GPU-related files first so patching feels grounded and fast." />
              )}
            </section>
          </div>
          ) : null}
        </section>
      </main>

      <PricingSection />

      <footer className="site-footer">
        <div className="site-footer-brand">
          <strong>ROCmPorter Agent</strong>
          <span>Evidence-driven CUDA → AMD ROCm migration reports and reviewable patches.</span>
        </div>
        <span className="site-footer-note">
          Scans run on your backend. AI patches use your configured model provider.
        </span>
      </footer>
    </div>
  )
}

const PRICING_TIERS = [
  {
    name: 'Free',
    price: '$0',
    cadence: 'forever',
    tagline: 'For trying it on public repos.',
    features: [
      'Unlimited public GitHub repo scans',
      'Full ROCm readiness score & findings',
      'Migration checklist & GPU signal list',
      'Offline HTML / JSON / Markdown export',
    ],
    cta: 'Start scanning',
    href: '#workspace',
    highlighted: false,
  },
  {
    name: 'Pro',
    price: '$29',
    cadence: 'per month',
    tagline: 'For engineers shipping the migration.',
    features: [
      'Everything in Free',
      'AI-generated single-file ROCm patches',
      'Patch verification & safe apply / rollback',
      'GitHub-ready PR review artifacts',
      'Private repository scanning (PAT)',
    ],
    cta: 'Upgrade to Pro',
    href: '#pricing',
    highlighted: true,
  },
  {
    name: 'Team',
    price: 'Custom',
    cadence: 'contact us',
    tagline: 'For teams porting many repos.',
    features: [
      'Everything in Pro',
      'CI/CD scan + patch pipelines',
      'AMD Developer Cloud ROCm validation',
      'Shared audit bundles & seats',
      'Priority support',
    ],
    cta: 'Talk to us',
    href: 'mailto:sales@rocmporter.app',
    highlighted: false,
  },
]

function PricingSection() {
  return (
    <section id="pricing" className="pricing">
      <div className="pricing-head">
        <p className="section-label">Pricing</p>
        <h2>Start free. Pay when you ship patches.</h2>
        <p className="pricing-sub">
          Scanning real repositories is always free. Paid plans unlock AI patch generation, verified apply,
          and GitHub review automation.
        </p>
      </div>
      <div className="pricing-grid">
        {PRICING_TIERS.map((tier) => (
          <article key={tier.name} className={`price-card${tier.highlighted ? ' featured' : ''}`}>
            {tier.highlighted ? <span className="price-badge">Most popular</span> : null}
            <h3>{tier.name}</h3>
            <div className="price-amount">
              <span className="price-value">{tier.price}</span>
              <span className="price-cadence">{tier.cadence}</span>
            </div>
            <p className="price-tagline">{tier.tagline}</p>
            <ul className="price-features">
              {tier.features.map((feature) => (
                <li key={feature}>{feature}</li>
              ))}
            </ul>
            <a className={tier.highlighted ? 'primary-button price-cta' : 'secondary-button price-cta'} href={tier.href}>
              {tier.cta}
            </a>
          </article>
        ))}
      </div>
    </section>
  )
}

function EmptyState({ text }) {
  return <p className="empty-state">{text}</p>
}

function SamplePreviewNote({ text }) {
  return (
    <div className="warning-banner low">
      <strong>sample preview</strong>
      <span>{text}</span>
    </div>
  )
}

function SystemStatusChips({ apiHealth, ollamaStatus }) {
  const apiLabel = apiHealth === 'ok' ? 'API online' : apiHealth === 'error' ? 'API offline' : 'API checking'
  const ollamaLabel = ollamaStatus?.reachable
    ? ollamaStatus.preferredModel?.loaded
      ? 'Ollama ready'
      : 'Ollama online'
    : ollamaStatus
      ? 'Ollama offline'
      : 'Ollama checking'

  return (
    <div className="system-status-row" aria-label="System status">
      <span className={`status-chip ${apiHealth === 'ok' ? 'online' : apiHealth === 'error' ? 'offline' : 'checking'}`}>
        {apiLabel}
      </span>
      <span
        className={`status-chip ${
          ollamaStatus?.reachable ? (ollamaStatus.preferredModel?.loaded ? 'online' : 'warm') : ollamaStatus ? 'offline' : 'checking'
        }`}
      >
        {ollamaLabel}
      </span>
    </div>
  )
}

function SeverityBreakdown({ findings }) {
  if (!findings?.length) {
    return null
  }

  const counts = countBySeverity(findings)
  const total = findings.length
  const severities = ['critical', 'high', 'medium', 'low']

  return (
    <div className="severity-breakdown">
      <div className="severity-bar" aria-label="Finding severity distribution">
        {severities.map((severity) =>
          counts[severity] ? (
            <div
              key={severity}
              className={`severity-segment ${severity}`}
              style={{ flexGrow: counts[severity] }}
              title={`${severity}: ${counts[severity]}`}
            />
          ) : null,
        )}
      </div>
      <div className="severity-legend">
        {severities.map((severity) =>
          counts[severity] ? (
            <span key={severity} className={`legend-item ${severity}`}>
              {severity} ({counts[severity]})
            </span>
          ) : null,
        )}
        <span className="legend-total">{total} total</span>
      </div>
    </div>
  )
}

function buildExecutiveSummary(report) {
  if (!report) {
    return ''
  }

  const { findings, summary, build, repo } = report
  const priorityCount = findings.filter((finding) => finding.severity === 'critical' || finding.severity === 'high').length
  const topFinding =
    findings.find((finding) => finding.severity === 'critical' || finding.severity === 'high') ?? findings[0] ?? null
  const signalPreview = (build.gpuSignals ?? []).slice(0, 3)
  const extraSignals = Math.max(0, (build.gpuSignals?.length ?? 0) - signalPreview.length)

  const sentences = [
    `Repository "${repo.name}" scores ${summary.portabilityScore}/100 for ROCm portability with ${summary.riskLevel} overall risk.`,
    findings.length
      ? `The scan surfaced ${findings.length} compatibility signal${findings.length === 1 ? '' : 's'}${priorityCount ? `, including ${priorityCount} high-priority item${priorityCount === 1 ? '' : 's'}` : ''}.`
      : 'No CUDA-specific blockers were detected by the current ruleset.',
  ]

  if (topFinding) {
    sentences.push(`Primary focus: ${topFinding.title}.`)
  }

  if (signalPreview.length) {
    sentences.push(
      `Start with ${signalPreview.join(', ')}${extraSignals ? ` and ${extraSignals} more GPU-related file${extraSignals === 1 ? '' : 's'}` : ''}.`,
    )
  }

  sentences.push(`Estimated migration effort: ${summary.estimatedEffort}.`)
  return sentences.join(' ')
}

function diffLineClass(line) {
  if (line.startsWith('+++') || line.startsWith('---')) return 'diff-line file'
  if (line.startsWith('@@')) return 'diff-line hunk'
  if (line.startsWith('+')) return 'diff-line add'
  if (line.startsWith('-')) return 'diff-line del'
  if (line.startsWith('diff ') || line.startsWith('index ')) return 'diff-line meta'
  return 'diff-line'
}

function DiffView({ text }) {
  return (
    <pre className="diff-code">
      {text.split('\n').map((line, index) => (
        <span key={index} className={diffLineClass(line)}>
          {line}
          {'\n'}
        </span>
      ))}
    </pre>
  )
}

function scoreToneClass(score) {
  if (typeof score !== 'number') {
    return ''
  }
  if (score >= 75) {
    return 'score-good'
  }
  if (score >= 50) {
    return 'score-mid'
  }
  return 'score-low'
}

function BenchmarkProofPanel({ proof }) {
  return (
    <section className="benchmark-proof-bar" aria-labelledby="benchmark-proof-heading">
      <div className="proof-bar-copy">
        <div>
          <p className="section-label">Benchmark Proof</p>
          <h3 id="benchmark-proof-heading">{proof.headline}</h3>
        </div>
        <p className="status-hint">{proof.summary}</p>
      </div>

      <div className="proof-bar-metrics" aria-label={`${proof.runName} benchmark summary`}>
        {proof.totals.map((metric) => (
          <div key={metric.label} className="proof-bar-metric">
            <span className="metric-label">{metric.label}</span>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </div>

      <p className="status-hint proof-run-path">
        {proof.runName} - {proof.summaryPath}
      </p>
    </section>
  )
}

function countBySeverity(findings) {
  return findings.reduce(
    (counts, finding) => ({
      ...counts,
      [finding.severity]: (counts[finding.severity] ?? 0) + 1,
    }),
    {},
  )
}

function isPatchInFlight(patchJob) {
  return patchJob?.status === 'queued' || patchJob?.status === 'running'
}

function patchActionLabel(patchJob, pendingPatchTarget, findingId, evidencePath, isRequestingPatch) {
  const activeTarget =
    pendingPatchTarget ??
    (isPatchInFlight(patchJob)
      ? {
          findingId: patchJob.findingId,
          evidencePath: patchJob.evidencePath,
        }
      : null)

  if (activeTarget?.findingId === findingId && activeTarget?.evidencePath === evidencePath) {
    return isRequestingPatch ? 'Starting Patch...' : 'Generating Patch...'
  }

  return 'Generate Patch'
}

function prioritizeExportFiles(files) {
  const rank = {
    html_report: 1,
    zip_bundle: 2,
    github_review_markdown: 3,
    github_review_json: 4,
    github_inline_comments_json: 5,
    report_json: 6,
    summary_markdown: 7,
    patch_diff: 8,
    patch_json: 9,
    manifest: 10,
    checksums: 11,
  }
  return [...files].sort((left, right) => {
    const leftRank = rank[left.kind] ?? 99
    const rightRank = rank[right.kind] ?? 99
    return leftRank - rightRank || left.label.localeCompare(right.label)
  })
}

function trimRepoUrl(repoUrl) {
  return repoUrl.replace('https://github.com/', '')
}

function formatLineRange(evidence) {
  if (!evidence.lineStart) {
    return 'Path-level signal'
  }
  if (!evidence.lineEnd || evidence.lineEnd === evidence.lineStart) {
    return `Line ${evidence.lineStart}`
  }
  return `Lines ${evidence.lineStart}-${evidence.lineEnd}`
}

function findActiveFinding(report, patchJob) {
  if (!report || !patchJob) {
    return null
  }
  return report.findings.find((finding) => finding.id === patchJob.findingId) ?? null
}

function chooseSelectedModel(current, models, resolvedName) {
  const availableNames = new Set(models.map((model) => model.name))
  if (current && availableNames.has(current)) {
    return current
  }
  if (resolvedName && availableNames.has(resolvedName)) {
    return resolvedName
  }

  const currentBase = baseModelName(current)
  const baseMatch = models.find((model) => baseModelName(model.name) === currentBase)
  return baseMatch?.name ?? models[0]?.name ?? FALLBACK_MODEL
}

function deriveOllamaReadiness(status, selectedModel) {
  if (!status) {
    return {
      kind: 'checking',
      label: 'Checking',
      message: 'Checking the local Ollama service and selected coding model.',
      severity: 'low',
      canGenerate: false,
      canWarm: false,
    }
  }

  if (!status.reachable) {
    return {
      kind: 'unavailable',
      label: 'Ollama unavailable',
      message: status.error ?? 'Ollama is not reachable locally. Patch generation will fail until the local service is running.',
      severity: 'high',
      canGenerate: false,
      canWarm: false,
    }
  }

  const preferred = status.preferredModel
  if (!preferred?.available) {
    return {
      kind: 'missing',
      label: 'Model missing',
      message: `${selectedModel} is not installed locally. Pull it first or choose one of the installed models.`,
      severity: 'high',
      canGenerate: false,
      canWarm: false,
    }
  }

  const activeModel = status.models?.find((model) => model.name === preferred.resolvedName) ?? null
  if (preferred.loaded) {
    return {
      kind: 'ready',
      label: 'Ready now',
      message: `${preferred.resolvedName} is ready for single-file patch generation.`,
      severity: 'low',
      canGenerate: true,
      canWarm: false,
    }
  }

  if (isLikelySlowModel(activeModel)) {
    return {
      kind: 'slow',
      label: 'Likely slow',
      message: `${preferred.resolvedName} is installed, but it is large for evidence-file patching. Expect slower first-patch turnarounds.`,
      severity: 'medium',
      canGenerate: true,
      canWarm: true,
    }
  }

    return {
      kind: 'cold',
      label: 'Cold start likely',
      message: `Ollama is running, but ${preferred.resolvedName} is not warm yet. The first patch may spend much of the backend time budget loading it.`,
      severity: 'medium',
      canGenerate: true,
      canWarm: true,
    }
}

function buildFallbackOllamaStatus(requestedModel, error) {
  return {
    host: 'Local Ollama',
    reachable: false,
    checkedAt: new Date().toISOString(),
    responseTimeMs: null,
    version: null,
    preferredModel: {
      requestedName: requestedModel,
      resolvedName: null,
      available: false,
      loaded: false,
    },
    modelCount: 0,
    loadedModelCount: 0,
    models: [],
    runningModels: [],
    summary: 'Ollama is not reachable locally.',
    error,
  }
}

function formatOllamaMeta(status) {
  if (!status) {
    return 'Checking the local Ollama service.'
  }

  if (!status.reachable) {
    return 'Local patch generation is paused until Ollama responds again.'
  }

  const parts = []
  if (status.version) {
    parts.push(`Ollama ${status.version}`)
  }
  if (status.host) {
    parts.push(status.host)
  }
  if (status.responseTimeMs) {
    parts.push(`${status.responseTimeMs} ms`)
  }
  parts.push(`${status.loadedModelCount ?? 0} warm`)
  return parts.join(' - ')
}

function buildPatchStatusCopy(patchJob, pendingPatchTarget, selectedModel, ollamaReadiness) {
  if (patchJob) {
    const stageSuffix = patchJob.stage ? ` — ${humanizeStatus(patchJob.stage).toLowerCase()}` : ''
    return `${humanizeStatus(patchJob.status)}${stageSuffix} · ${patchJob.evidencePath} · ${patchJob.model}`
  }

  if (pendingPatchTarget) {
    return `Starting a patch request for ${pendingPatchTarget.evidencePath} with ${selectedModel}${patchReadinessSuffix(ollamaReadiness)}`
  }

  return `Choose one evidence file to produce a single-file diff and save it as a patch artifact.${patchReadinessSuffix(ollamaReadiness)}`
}

function patchReadinessSuffix(ollamaReadiness) {
  if (ollamaReadiness.kind === 'cold') {
    return ' First run may spend much of the backend time budget loading the model.'
  }
  if (ollamaReadiness.kind === 'slow') {
    return ' This selected model may take longer on the first generation.'
  }
  if (ollamaReadiness.kind === 'unavailable') {
    return ' Local Ollama must be reachable before patch generation can start.'
  }
  return ''
}

function getApplyBlockReason(patchJob, patchApply) {
  if (!patchJob || patchJob.status !== 'completed') {
    return ''
  }
  if (patchApply?.status === 'applied' && patchApply.patchId !== patchJob.patchId) {
    return ''
  }
  if (!patchJob.savedPatchedFilePath) {
    return 'Apply is blocked because this patch does not include a saved patched file snapshot.'
  }
  if (patchJob.validation?.state === 'failed') {
    return 'Apply is blocked because this patch failed local syntax validation.'
  }
  if (hasResponseArtifactLeak(patchJob)) {
    return 'Apply is blocked because this patch still contains leaked model control text.'
  }
  return ''
}

function hasResponseArtifactLeak(patchJob) {
  return Boolean(patchJob?.warnings?.some((warning) => warning.code === 'response_artifact_leak'))
}

function getVerificationBlockReason(patchJob, verification, action) {
  if (!patchJob || patchJob.status !== 'completed') {
    return ''
  }
  if (!verification || verification.patchId !== patchJob.patchId) {
    return `Verify this patch before ${action === 'export' ? 'exporting it' : 'applying it'}.`
  }
  if (action === 'export' && !verification.exportReady) {
    return 'Verification says this patch is not export-ready.'
  }
  if (action === 'apply' && !verification.applyReady) {
    return 'Verification says this patch is not apply-ready.'
  }
  return ''
}

function getGitHubReviewBlockReason({ patchJob, verification, exportBlockReason, isDemoMode }) {
  if (!patchJob || patchJob.status !== 'completed') {
    return 'Generate a completed patch before building a GitHub review artifact.'
  }
  if (isDemoMode) {
    return ''
  }
  if (!verification || verification.patchId !== patchJob.patchId) {
    return 'Verify this patch before building a GitHub review artifact.'
  }
  if (exportBlockReason) {
    return exportBlockReason
  }
  if (!verification.exportReady) {
    return 'Patch verification is not export-ready.'
  }
  return ''
}

function buildPatchDecisionSummary({ patchJob, verification, applyBlockReason, exportBlockReason, isDemoMode }) {
  if (!patchJob || patchJob.status !== 'completed') {
    return null
  }

  if (isDemoMode) {
    return {
      label: 'Sample Preview',
      title: 'Preview the review flow, not a live workspace write',
      message:
        'This is sample-mode evidence for the demo path. Export artifacts are illustrative and workspace apply stays blocked until you run a live repository scan.',
      severity: 'low',
      applyReady: false,
      exportReady: Boolean(verification?.exportReady),
    }
  }

  if (!verification) {
    return {
      label: 'Decision',
      title: 'Verification required before apply or export',
      message: 'Run Verify Patch first so the app can record syntax, diff replay, and semantic sanity checks for this artifact.',
      severity: 'medium',
      applyReady: false,
      exportReady: false,
    }
  }

  const firstFailedCheck = verification.checks.find((check) => check.state === 'failed')
  const firstWarningCheck = verification.checks.find((check) => check.state === 'warning')
  const blocker = firstFailedCheck ?? firstWarningCheck ?? null

  if (verification.applyReady && verification.exportReady) {
    return {
      label: 'Decision',
      title: 'Patch is ready for export and workspace apply',
      message: blocker ? `${blocker.label}: ${blocker.message}` : 'Verification passed. Keep the receipt and diff with the patch artifact.',
      severity: 'low',
      applyReady: true,
      exportReady: true,
    }
  }

  if (verification.exportReady && !verification.applyReady) {
    if (patchJob.patchMode === 'partial') {
      return {
        label: 'Safe Partial Patch',
        title: 'Conservative review artifact, not a complete ROCm fix',
        message:
          'This diff only covers the selected evidence file and is meant for review/export, not full migration proof.',
        severity: 'medium',
        applyReady: false,
        exportReady: true,
      }
    }
    return {
      label: 'Decision',
      title: 'Export allowed, apply blocked',
      message:
        blocker?.message ??
        applyBlockReason ??
        'Verification allows artifact export, but this patch still needs more review before a workspace write.',
      severity: 'medium',
      applyReady: false,
      exportReady: true,
    }
  }

  return {
    label: 'Decision',
    title: 'Review blocked until the failing check is resolved',
    message:
      blocker?.message ??
      exportBlockReason ??
      applyBlockReason ??
      'Verification marked this patch as not ready for export or workspace apply.',
    severity: verification.state === 'failed' ? 'high' : 'medium',
    applyReady: Boolean(verification.applyReady),
    exportReady: Boolean(verification.exportReady),
  }
}

function buildOllamaFacts(status) {
  if (!status) {
    return []
  }

  const preferred = status.preferredModel ?? {}
  const runningModel = status.runningModels?.[0] ?? null
  const resolvedModel =
    preferred.requestedName && preferred.resolvedName && preferred.requestedName !== preferred.resolvedName
      ? `${preferred.requestedName} -> ${preferred.resolvedName}`
      : preferred.resolvedName ?? preferred.requestedName ?? 'n/a'

  return [
    { label: 'Last checked', value: formatTimestamp(status.checkedAt) },
    { label: 'Model route', value: resolvedModel },
    { label: 'Warm models', value: `${status.loadedModelCount ?? 0}/${status.modelCount ?? 0}` },
    { label: 'Response time', value: status.responseTimeMs ? `${status.responseTimeMs} ms` : 'n/a' },
    { label: 'Running', value: runningModel?.name ?? 'none' },
    { label: 'Processor', value: runningModel?.processor ?? 'n/a' },
  ]
}

function formatTimestamp(value) {
  if (!value) {
    return 'n/a'
  }
  return new Date(value).toLocaleString()
}

function verificationLabel(verification) {
  if (verification.exportReady && !verification.applyReady) {
    return 'apply gate blocked'
  }
  return `verification ${verification.state}`
}

function verificationSeverity(verification) {
  if (verification.exportReady && !verification.applyReady) {
    return 'medium'
  }
  if (verification.state === 'failed') {
    return 'high'
  }
  if (verification.state === 'warning') {
    return 'medium'
  }
  return 'low'
}

function isLikelySlowModel(model) {
  if (!model) {
    return false
  }

  const rawParameterSize = typeof model.details?.parameterSize === 'string' ? model.details.parameterSize : ''
  const parameterSizeMatch = rawParameterSize.match(/([\d.]+)/)
  const parameterSize = parameterSizeMatch ? Number(parameterSizeMatch[1]) : null

  return Boolean((typeof model.size === 'number' && model.size >= 7_000_000_000) || (parameterSize && parameterSize >= 14))
}

function baseModelName(name) {
  return (name ?? '').split(':', 1)[0].trim().toLowerCase()
}

export default App
