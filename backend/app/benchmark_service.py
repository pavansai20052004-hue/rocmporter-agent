from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .export_service import export_service
from .models import EvidenceItem, Finding, PatchResult, PatchVerificationReceipt, ScanReport
from .patch_service import patch_service
from .service import WORK_ROOT, scan_service


BENCHMARK_ROOT = WORK_ROOT / "benchmarks"

_PREFERRED_SUFFIX_ORDER = {
    ".py": 0,
    ".toml": 1,
    ".txt": 2,
    ".json": 3,
    ".yml": 4,
    ".yaml": 5,
    ".cmake": 6,
    ".js": 7,
    ".ts": 8,
    ".tsx": 9,
    ".jsx": 10,
    ".cpp": 11,
    ".hpp": 12,
    ".h": 13,
    ".cuh": 14,
    ".cu": 15,
}


class BenchmarkService:
    def __init__(self) -> None:
        BENCHMARK_ROOT.mkdir(parents=True, exist_ok=True)

    def run_case_file(
        self,
        case_file: Path,
        *,
        model: str,
        export_formats: set[str],
        output_dir: Path | None = None,
    ) -> dict[str, Any]:
        cases = _load_case_file(case_file)
        run_root = output_dir or (BENCHMARK_ROOT / f"benchmark_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}")
        run_root.mkdir(parents=True, exist_ok=True)

        results: list[dict[str, Any]] = []
        started_at = datetime.now(UTC)
        for index, case in enumerate(cases, start=1):
            results.append(self._run_case(case, model=model, export_formats=export_formats, run_root=run_root, index=index))
            _write_summary_files(
                run_root,
                _build_summary(
                    case_file,
                    model,
                    export_formats,
                    run_root,
                    started_at,
                    results,
                    total_cases=len(cases),
                    run_status="running" if index < len(cases) else "completed",
                ),
            )

        summary = _build_summary(
            case_file,
            model,
            export_formats,
            run_root,
            started_at,
            results,
            total_cases=len(cases),
            run_status="completed",
        )
        _write_summary_files(run_root, summary)
        return summary

    def _run_case(
        self,
        case: dict[str, Any],
        *,
        model: str,
        export_formats: set[str],
        run_root: Path,
        index: int,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        label = str(case.get("name") or f"case-{index}")
        artifact_dir = run_root / f"{index:02d}-{_slugify(label)}"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        result: dict[str, Any] = {
            "name": label,
            "repoUrl": case["repoUrl"],
            "note": case.get("note"),
            "findingIdRequested": case["findingId"],
            "evidencePathRequested": case.get("evidencePath"),
            "artifactDir": str(artifact_dir.resolve()),
            "status": "running",
            "startedAt": datetime.now(UTC).isoformat(),
        }

        try:
            scan_status, report = scan_service.run_scan_blocking(case["repoUrl"])
            result["scanId"] = scan_status.scanId
            result["portabilityScore"] = report.summary.portabilityScore
            result["scanRiskLevel"] = report.summary.riskLevel

            finding = next((item for item in report.findings if item.id == case["findingId"]), None)
            if finding is None:
                result["status"] = "finding_missing"
                result["error"] = f"Finding {case['findingId']} was not detected in this repository."
                return _finalize_case_result(result, started)

            result["findingIdResolved"] = finding.id
            evidence = _select_evidence(finding, case.get("evidencePath"))
            if evidence is None:
                result["status"] = "evidence_missing"
                result["error"] = "No matching evidence file was available for the requested finding."
                return _finalize_case_result(result, started)

            result["evidencePathResolved"] = evidence.path
            patch = patch_service.run_patch_blocking(scan_status.scanId, finding.id, evidence.path, model)
            result.update(_patch_payload(patch))
            if patch.status != "completed":
                result["status"] = "failed"
                result["primaryFailure"] = _primary_failure_from_patch(patch)
                return _finalize_case_result(result, started)

            verification = patch_service.verify_patch(scan_status.scanId, patch.patchId)
            result.update(_verification_payload(verification))

            export_result, export_error = _try_create_export(scan_status.scanId, patch.patchId, export_formats, artifact_dir)
            if export_result is not None:
                result["status"] = "completed"
                result["exportId"] = export_result.exportId
                result["bundleFileCount"] = len(export_result.files)
                result["exportRoot"] = export_result.rootPath
            else:
                result["status"] = "export_blocked"
                result["exportError"] = export_error

            return _finalize_case_result(result, started)
        except Exception as exc:  # pragma: no cover - operational benchmark guardrail
            result["status"] = "failed"
            result["error"] = str(exc).strip() or exc.__class__.__name__
            return _finalize_case_result(result, started)


def _load_case_file(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Benchmark case file must contain a non-empty 'cases' array.")

    normalized: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"Benchmark case {index} is not an object.")
        repo_url = case.get("repoUrl")
        finding_id = case.get("findingId")
        if not isinstance(repo_url, str) or not repo_url.strip():
            raise ValueError(f"Benchmark case {index} is missing repoUrl.")
        if not isinstance(finding_id, str) or not finding_id.strip():
            raise ValueError(f"Benchmark case {index} is missing findingId.")
        normalized.append(
            {
                "name": case.get("name") or f"case-{index}",
                "repoUrl": repo_url.strip(),
                "findingId": finding_id.strip(),
                "evidencePath": case.get("evidencePath"),
                "note": case.get("note"),
            }
        )
    return normalized


def _select_evidence(finding: Finding, requested_path: str | None) -> EvidenceItem | None:
    if requested_path:
        return next((item for item in finding.evidence if item.path == requested_path), None)
    if not finding.evidence:
        return None
    if finding.id == "cuda_build_config":
        return min(finding.evidence, key=_build_config_evidence_sort_key)
    return min(finding.evidence, key=_evidence_sort_key)


def _evidence_sort_key(evidence: EvidenceItem) -> tuple[int, int, int, str]:
    suffix = Path(evidence.path).suffix.lower()
    suffix_rank = _PREFERRED_SUFFIX_ORDER.get(suffix, 99)
    span = (evidence.lineEnd or evidence.lineStart or 999999) - (evidence.lineStart or 0)
    line = evidence.lineStart or 999999
    return (suffix_rank, span, line, evidence.path.lower())


def _build_config_evidence_sort_key(evidence: EvidenceItem) -> tuple[int, int, int, int, int, int, str]:
    path = Path(evidence.path)
    parts = [part.lower() for part in path.parts]
    path_lower = evidence.path.lower()
    snippet = (evidence.snippet or "").lower()
    match_text = (evidence.matchText or "").lower()
    combined_text = "\n".join([path_lower, snippet, match_text])

    if path.name.lower() == "setup.py" and len(path.parts) == 1:
        surface_rank = 0
    elif path.name.lower() == "cmakelists.txt" and len(path.parts) == 1:
        surface_rank = 1
    elif path.name.lower() == "setup.py":
        surface_rank = 2
    elif path.name.lower() == "cmakelists.txt":
        surface_rank = 3
    else:
        surface_rank = 6

    has_rocm_context = any(token in combined_text for token in ["rocm", "hip", "is_rocm"])
    generated_source_penalty = 1 if any(
        segment in {"csrc", "src", "include", "benchmarks", "test", "tests", ".github", "workflows"}
        for segment in parts
    ) else 0

    span = (evidence.lineEnd or evidence.lineStart or 999999) - (evidence.lineStart or 0)
    line = evidence.lineStart or 999999
    depth = len(path.parts)
    return (
        surface_rank,
        0 if has_rocm_context else 1,
        generated_source_penalty,
        depth,
        span,
        line,
        path_lower,
    )


def _patch_payload(patch: PatchResult) -> dict[str, Any]:
    warning_codes = [item.code for item in patch.warnings]
    return {
        "patchId": patch.patchId,
        "patchStatus": patch.status,
        "patchError": patch.error,
        "patchValidationState": patch.validation.state if patch.validation else None,
        "patchValidationTool": patch.validation.tool if patch.validation else None,
        "patchWarningCodes": warning_codes,
        "patchWarningCount": len(warning_codes),
        "patchRiskScore": patch.riskAssessment.score if patch.riskAssessment else None,
        "patchRiskLevel": patch.riskAssessment.level if patch.riskAssessment else None,
        "patchSavedPath": patch.savedPatchPath,
    }


def _verification_payload(verification: PatchVerificationReceipt) -> dict[str, Any]:
    failed_checks = [check.code for check in verification.checks if check.state == "failed"]
    warning_checks = [check.code for check in verification.checks if check.state == "warning"]
    return {
        "verificationReceiptId": verification.receiptId,
        "verificationState": verification.state,
        "applyReady": verification.applyReady,
        "exportReady": verification.exportReady,
        "failedCheckCodes": failed_checks,
        "warningCheckCodes": warning_checks,
        "primaryFailure": _primary_failure_from_receipt(verification),
        "savedReceiptPath": verification.savedReceiptPath,
    }


def _try_create_export(
    scan_id: str,
    patch_id: str,
    export_formats: set[str],
    artifact_dir: Path,
) -> tuple[Any | None, str | None]:
    try:
        return (
            export_service.create_export(
                scan_id,
                patch_id=patch_id,
                formats=export_formats,
                output_dir=artifact_dir,
            ),
            None,
        )
    except ValueError as exc:
        return None, str(exc)


def _finalize_case_result(result: dict[str, Any], started: float) -> dict[str, Any]:
    if not result.get("primaryFailure"):
        result["primaryFailure"] = _fallback_primary_failure(result)
    result["qualityLane"] = _quality_lane(result)
    result["judgeSignal"] = _judge_signal(result)
    result["finishedAt"] = datetime.now(UTC).isoformat()
    result["durationSeconds"] = round(time.perf_counter() - started, 2)
    return result


def _build_summary(
    case_file: Path,
    model: str,
    export_formats: set[str],
    run_root: Path,
    started_at: datetime,
    results: list[dict[str, Any]],
    *,
    total_cases: int,
    run_status: str,
) -> dict[str, Any]:
    totals = _summarize_results(results)
    totals["plannedCaseCount"] = total_cases
    totals["remainingCaseCount"] = max(0, total_cases - len(results))
    return {
        "runStatus": run_status,
        "generatedAt": datetime.now(UTC).isoformat(),
        "startedAt": started_at.isoformat(),
        "caseFile": str(case_file.resolve()),
        "model": model,
        "exportFormats": sorted(export_formats),
        "runRoot": str(run_root.resolve()),
        "totals": totals,
        "cases": results,
    }


def _write_summary_files(run_root: Path, summary: dict[str, Any]) -> None:
    (run_root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_root / "summary.md").write_text(_build_summary_markdown(summary), encoding="utf-8")


def _summarize_results(results: list[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "caseCount": len(results),
        "plannedCaseCount": len(results),
        "remainingCaseCount": 0,
        "completed": 0,
        "exportBlocked": 0,
        "findingMissing": 0,
        "evidenceMissing": 0,
        "failed": 0,
        "applyReady": 0,
        "exportReady": 0,
        "highRisk": 0,
        "mediumRisk": 0,
        "lowRisk": 0,
        "applyReadyCases": 0,
        "reviewReadyCases": 0,
        "blockedCases": 0,
        "scannerGapCases": 0,
        "generationFailedCases": 0,
        "infrastructureFailedCases": 0,
    }
    for item in results:
        status = item.get("status")
        if status == "completed":
            totals["completed"] += 1
        elif status == "export_blocked":
            totals["exportBlocked"] += 1
        elif status == "finding_missing":
            totals["findingMissing"] += 1
        elif status == "evidence_missing":
            totals["evidenceMissing"] += 1
        elif status == "failed":
            totals["failed"] += 1

        if item.get("applyReady"):
            totals["applyReady"] += 1
        if item.get("exportReady"):
            totals["exportReady"] += 1

        risk = item.get("patchRiskLevel")
        if risk == "high":
            totals["highRisk"] += 1
        elif risk == "medium":
            totals["mediumRisk"] += 1
        elif risk == "low":
            totals["lowRisk"] += 1

        lane = item.get("qualityLane")
        if lane == "apply-ready":
            totals["applyReadyCases"] += 1
        elif lane == "review-ready":
            totals["reviewReadyCases"] += 1
        elif lane == "blocked":
            totals["blockedCases"] += 1
        elif lane == "scanner-gap":
            totals["scannerGapCases"] += 1
        elif lane == "generation-failed":
            totals["generationFailedCases"] += 1
        elif lane == "infrastructure-failed":
            totals["infrastructureFailedCases"] += 1
    return totals


def _build_summary_markdown(summary: dict[str, Any]) -> str:
    totals = summary["totals"]
    lines = [
        "# ROCmPorter Benchmark Summary",
        "",
        f"- Run status: {summary.get('runStatus', 'completed')}",
        f"- Generated: {summary['generatedAt']}",
        f"- Cases completed: {totals['caseCount']} / {totals.get('plannedCaseCount', totals['caseCount'])}",
        f"- Remaining cases: {totals.get('remainingCaseCount', 0)}",
        f"- Completed exports: {totals['completed']}",
        f"- Export blocked: {totals['exportBlocked']}",
        f"- Apply ready: {totals['applyReady']}",
        f"- Export ready: {totals['exportReady']}",
        f"- Review-ready artifacts: {totals['reviewReadyCases']}",
        f"- Blocked cases: {totals['blockedCases']}",
        f"- Scanner gaps: {totals['scannerGapCases']}",
        f"- Generation failures: {totals['generationFailedCases']}",
        f"- Infrastructure failures: {totals['infrastructureFailedCases']}",
        f"- High risk patches: {totals['highRisk']}",
        f"- Medium risk patches: {totals['mediumRisk']}",
        f"- Low risk patches: {totals['lowRisk']}",
        "",
        "## Cases",
        "",
        "| Case | Status | Quality lane | Risk | Apply | Export | Judge signal |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in summary["cases"]:
        lines.append(
            "| "
            f"{case['name']} | "
            f"{case['status']} | "
            f"{case.get('qualityLane', 'unknown')} | "
            f"{case.get('patchRiskLevel', 'n/a')} | "
            f"{case.get('applyReady', False)} | "
            f"{case.get('exportReady', False)} | "
            f"{_markdown_cell(case.get('judgeSignal', 'No signal recorded.'))} |"
        )
        if case.get("primaryFailure"):
            failure = case["primaryFailure"]
            lines.append(f"  - primary failure: {failure['label']} - {failure['message']}")
        if case.get("error"):
            lines.append(f"  - error: {case['error']}")
        elif case.get("exportError"):
            lines.append(f"  - export: {case['exportError']}")
    return "\n".join(lines) + "\n"


def _quality_lane(result: dict[str, Any]) -> str:
    if result.get("status") == "completed" and result.get("applyReady"):
        return "apply-ready"
    if result.get("status") == "completed" and result.get("exportReady"):
        return "review-ready"
    if result.get("status") == "export_blocked" or result.get("exportReady") is False:
        return "blocked"
    if result.get("status") in {"finding_missing", "evidence_missing"}:
        return "scanner-gap"
    if result.get("status") == "failed":
        failure = result.get("primaryFailure") or {}
        if failure.get("code") == "benchmark_error":
            return "infrastructure-failed"
        return "generation-failed"
    return "unknown"


def _judge_signal(result: dict[str, Any]) -> str:
    lane = _quality_lane(result)
    risk = result.get("patchRiskLevel") or "n/a"
    if lane == "apply-ready":
        return "Patch passed all local gates and can be applied to the scanned workspace copy."
    if lane == "review-ready":
        return f"Export-ready review artifact; workspace apply remains gated for ROCm validation. Risk={risk}."
    if lane == "blocked":
        failure = result.get("primaryFailure") or {}
        message = failure.get("message") or result.get("exportError") or "Verification blocked export."
        return f"Verification blocked this patch before it could be presented as shippable: {message}"
    if lane == "scanner-gap":
        return "Scanner or evidence selection missed the requested migration target."
    if lane == "generation-failed":
        failure = result.get("primaryFailure") or {}
        return failure.get("message") or "Patch generation did not produce a usable artifact."
    if lane == "infrastructure-failed":
        failure = result.get("primaryFailure") or {}
        return failure.get("message") or "Benchmark infrastructure failed before patch quality could be evaluated."
    return "No decisive quality signal recorded."


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _primary_failure_from_receipt(verification: PatchVerificationReceipt) -> dict[str, str] | None:
    failed = next(
        (
            check
            for check in verification.checks
            if check.state == "failed" and not (verification.exportReady and check.code == "apply_precheck")
        ),
        None,
    )
    if failed is not None:
        return {
            "code": failed.code,
            "label": failed.label,
            "message": failed.message,
        }

    warning = next(
        (
            check
            for check in verification.checks
            if check.state == "warning"
            and not (verification.exportReady and check.code in {"apply_precheck", "patch_scope", "syntax_validation"})
        ),
        None,
    )
    if warning is not None:
        return {
            "code": warning.code,
            "label": warning.label,
            "message": warning.message,
        }

    return None


def _fallback_primary_failure(result: dict[str, Any]) -> dict[str, str] | None:
    if result.get("patchStatus") == "failed" and result.get("patchError"):
        return {
            "code": "patch_generation_failed",
            "label": "Patch Generation Failed",
            "message": str(result["patchError"]),
        }
    if result.get("error"):
        return {
            "code": "benchmark_error",
            "label": "Benchmark Error",
            "message": str(result["error"]),
        }
    if result.get("exportError"):
        return {
            "code": "export_blocked",
            "label": "Export Blocked",
            "message": str(result["exportError"]),
        }
    return None


def _primary_failure_from_patch(patch: PatchResult) -> dict[str, str]:
    return {
        "code": "patch_generation_failed",
        "label": "Patch Generation Failed",
        "message": patch.error or "Patch generation did not complete successfully.",
    }


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "case"


benchmark_service = BenchmarkService()
