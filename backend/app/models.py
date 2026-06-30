from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Severity = Literal["critical", "high", "medium", "low"]
ScanState = Literal["queued", "running", "completed", "failed"]
PatchState = Literal["queued", "running", "completed", "failed"]
ApplyState = Literal["applied", "rolled_back", "failed"]
ValidationState = Literal["passed", "failed", "unsupported"]
VerificationState = Literal["passed", "warning", "failed"]
RiskLevel = Literal["low", "medium", "high"]
ExportFormat = Literal["json", "markdown", "diff", "html", "zip", "github"]


class ScanRequest(BaseModel):
    repoUrl: str = Field(min_length=1, max_length=500)


class ScanProgress(BaseModel):
    stage: str
    percent: int = Field(ge=0, le=100)


class ScanStatus(BaseModel):
    scanId: str
    status: ScanState
    progress: ScanProgress
    repoUrl: str
    error: str | None = None


class RepositoryInfo(BaseModel):
    url: str
    name: str
    defaultBranch: str


class ReportSummary(BaseModel):
    portabilityScore: int
    riskLevel: Literal["low", "medium", "high"]
    estimatedEffort: str
    scanCompletedAt: datetime


class EvidenceItem(BaseModel):
    path: str
    lineStart: int | None = None
    lineEnd: int | None = None
    snippet: str | None = None
    matchText: str | None = None


class Finding(BaseModel):
    id: str
    severity: Severity
    title: str
    evidence: list[EvidenceItem]
    recommendation: str
    details: str
    confidence: Literal["high", "medium", "low"]


class BuildProfile(BaseModel):
    languages: list[str]
    buildSystems: list[str]
    gpuSignals: list[str]


class CoverageSummary(BaseModel):
    totalFiles: int = 0
    scannedFiles: int = 0
    skippedLargeFiles: int = 0
    skippedDirectories: list[str] = Field(default_factory=list)
    supportedTextExtensions: list[str] = Field(default_factory=list)


class ScanReport(BaseModel):
    repo: RepositoryInfo
    summary: ReportSummary
    findings: list[Finding]
    build: BuildProfile
    nextSteps: list[str]
    coverage: CoverageSummary | None = None
    rulesetVersion: str = "2026.06.29"


class PatchRequest(BaseModel):
    findingId: str = Field(min_length=1)
    evidencePath: str = Field(min_length=1)
    model: str | None = None


class PatchApplyRequest(BaseModel):
    patchId: str = Field(min_length=1)


class PatchStatus(BaseModel):
    patchId: str
    scanId: str
    findingId: str
    evidencePath: str
    model: str
    status: PatchState
    stage: str | None = None
    createdAt: datetime
    updatedAt: datetime
    error: str | None = None


class PatchValidation(BaseModel):
    state: ValidationState
    tool: str
    summary: str
    details: list[str] = Field(default_factory=list)


class PatchWarning(BaseModel):
    code: str
    severity: Severity
    message: str


class PatchRiskFactor(BaseModel):
    code: str
    label: str
    points: int = Field(ge=0, le=100)
    detail: str


class PatchRiskAssessment(BaseModel):
    score: int = Field(ge=0, le=100)
    level: RiskLevel
    summary: str
    reasons: list[str] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    factors: list[PatchRiskFactor] = Field(default_factory=list)


class PatchResult(PatchStatus):
    rationale: str | None = None
    diff: str | None = None
    savedPatchPath: str | None = None
    savedPatchedFilePath: str | None = None
    reviewRequired: bool = True
    warnings: list[PatchWarning] = Field(default_factory=list)
    validation: PatchValidation | None = None
    riskAssessment: PatchRiskAssessment | None = None
    changedLineCount: int | None = None
    changedHunkCount: int | None = None
    sourceFilePath: str | None = None
    sourceFileSha256: str | None = None


class PatchVerificationCheck(BaseModel):
    code: str
    label: str
    state: VerificationState
    message: str


class PatchVerificationReceipt(BaseModel):
    receiptId: str
    scanId: str
    patchId: str
    generatedAt: datetime
    state: VerificationState
    summary: str
    applyReady: bool
    exportReady: bool
    artifactHashes: dict[str, str] = Field(default_factory=dict)
    checks: list[PatchVerificationCheck] = Field(default_factory=list)
    savedReceiptPath: str | None = None


class OllamaModelInfo(BaseModel):
    name: str
    size: int | None = None
    modifiedAt: datetime | None = None
    digest: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    available: bool = True
    loaded: bool = False
    sizeVram: int | None = None
    expiresAt: datetime | None = None
    details: dict[str, str | int | list[str] | None] | None = None


class OllamaRunningModelInfo(BaseModel):
    name: str
    size: int | None = None
    processor: str | None = None
    context: int | None = None
    sizeVram: int | None = None
    expiresAt: datetime | None = None


class OllamaPreferredModelStatus(BaseModel):
    requestedName: str
    resolvedName: str | None = None
    available: bool = False
    loaded: bool = False


class OllamaHealthStatus(BaseModel):
    host: str
    reachable: bool
    checkedAt: datetime
    version: str | None = None
    responseTimeMs: int | None = None
    preferredModel: OllamaPreferredModelStatus
    modelCount: int = 0
    loadedModelCount: int = 0
    models: list[OllamaModelInfo] = Field(default_factory=list)
    runningModels: list[OllamaRunningModelInfo] = Field(default_factory=list)
    summary: str
    error: str | None = None


class OllamaWarmRequest(BaseModel):
    model: str = Field(min_length=1)


class ExportRequest(BaseModel):
    patchId: str | None = None
    formats: list[ExportFormat] = Field(default_factory=lambda: ["json", "markdown", "html", "zip", "github"])


class ExportFile(BaseModel):
    kind: str
    label: str
    path: str
    downloadPath: str | None = None


class ExportResult(BaseModel):
    exportId: str
    scanId: str
    patchId: str | None = None
    createdAt: datetime
    rootPath: str
    files: list[ExportFile] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GitHubReviewRequest(BaseModel):
    patchId: str = Field(min_length=1)
    repository: str | None = None
    pullRequestNumber: int | None = Field(default=None, ge=1)
    postComment: bool = False


class GitHubInlineComment(BaseModel):
    path: str
    line: int = Field(ge=1)
    side: Literal["RIGHT", "LEFT"] = "RIGHT"
    body: str
    severity: Severity
    source: Literal["evidence", "warning", "risk"]
    code: str


class GitHubReviewResult(BaseModel):
    reviewId: str
    scanId: str
    patchId: str
    repository: str
    pullRequestNumber: int | None = None
    createdAt: datetime
    riskScore: int = Field(ge=0, le=100)
    riskLevel: RiskLevel
    summary: str
    warnings: list[str] = Field(default_factory=list)
    commentBody: str
    savedMarkdownPath: str
    savedJsonPath: str
    savedInlineCommentsPath: str
    inlineCommentsCount: int = 0
    savedPrSafeInlineCommentsPath: str | None = None
    prSafeInlineCommentsCount: int = 0
    posted: bool = False
    postUrl: str | None = None
    postError: str | None = None


class PatchApplyResult(BaseModel):
    applyId: str
    scanId: str
    patchId: str
    status: ApplyState
    targetFilePath: str
    workspaceRoot: str
    backupFilePath: str
    appliedFilePath: str
    createdAt: datetime
    updatedAt: datetime
    rollbackAvailable: bool = True
    rollbackReason: str | None = None
    error: str | None = None
