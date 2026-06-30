from __future__ import annotations

import argparse
import json
from pathlib import Path

from .apply_service import apply_service
from .export_service import export_service
from .github_review_service import github_review_service
from .models import (
    ExportResult,
    GitHubReviewResult,
    PatchApplyResult,
    PatchResult,
    PatchVerificationReceipt,
    ScanReport,
    ScanStatus,
)
from .ollama_service import list_models
from .patch_service import DEFAULT_MODEL, patch_service
from .service import WORK_ROOT, scan_service

DEFAULT_EXPORTS = "json,md,diff,html,zip,github"


def main() -> None:
    parser = argparse.ArgumentParser(prog="rocmporter", description="ROCmPorter Agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Run a repository scan and export the report")
    scan_parser.add_argument("repo_url")
    scan_parser.add_argument("--out", default=None)
    scan_parser.add_argument("--export", default=DEFAULT_EXPORTS)
    scan_parser.add_argument("--json", action="store_true")

    run_parser = subparsers.add_parser("run", help="Run scan and optionally generate one patch")
    run_parser.add_argument("repo_url")
    run_parser.add_argument("--finding-id")
    run_parser.add_argument("--evidence-path")
    run_parser.add_argument("--model", default=DEFAULT_MODEL)
    run_parser.add_argument("--export", default=DEFAULT_EXPORTS)
    run_parser.add_argument("--out", default=None)
    run_parser.add_argument("--json", action="store_true")

    patch_parser = subparsers.add_parser("patch", help="Generate a patch from an existing scan")
    patch_parser.add_argument("scan_id")
    patch_parser.add_argument("--finding-id", required=True)
    patch_parser.add_argument("--evidence-path", required=True)
    patch_parser.add_argument("--model", default=DEFAULT_MODEL)
    patch_parser.add_argument("--export", default=DEFAULT_EXPORTS)
    patch_parser.add_argument("--out", default=None)
    patch_parser.add_argument("--json", action="store_true")

    repair_parser = subparsers.add_parser("repair-patch", help="Repair a completed patch by removing model response artifacts")
    repair_parser.add_argument("scan_id")
    repair_parser.add_argument("--patch-id", required=True)
    repair_parser.add_argument("--export", default=DEFAULT_EXPORTS)
    repair_parser.add_argument("--out", default=None)
    repair_parser.add_argument("--json", action="store_true")

    verify_parser = subparsers.add_parser("verify-patch", help="Create a verification receipt for a completed patch")
    verify_parser.add_argument("scan_id")
    verify_parser.add_argument("--patch-id", required=True)
    verify_parser.add_argument("--json", action="store_true")

    apply_parser = subparsers.add_parser("apply-patch", help="Apply a completed patch inside the scanned workspace copy")
    apply_parser.add_argument("scan_id")
    apply_parser.add_argument("--patch-id", required=True)
    apply_parser.add_argument("--json", action="store_true")

    rollback_parser = subparsers.add_parser("rollback-patch", help="Rollback a previously applied patch from its backup")
    rollback_parser.add_argument("--apply-id", required=True)
    rollback_parser.add_argument("--json", action="store_true")

    review_parser = subparsers.add_parser("github-review", help="Build a GitHub PR review comment artifact from a patch")
    review_parser.add_argument("scan_id")
    review_parser.add_argument("--patch-id", required=True)
    review_parser.add_argument("--repo", default=None)
    review_parser.add_argument("--pr-number", type=int, default=None)
    review_parser.add_argument("--post", action="store_true")
    review_parser.add_argument("--out", default=None)
    review_parser.add_argument("--json", action="store_true")

    models_parser = subparsers.add_parser("models", help="List local Ollama models")
    models_parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.command == "scan":
        status, report = scan_service.run_scan_blocking(args.repo_url)
        artifact_dir = _artifact_dir(args.out, status.scanId)
        export_result = export_service.create_export(
            status.scanId,
            formats=_parse_export_formats(args.export),
            output_dir=artifact_dir,
        )
        _print_scan_result(status, report, export_result, args.json, artifact_dir)
        return

    if args.command == "run":
        status, report = scan_service.run_scan_blocking(args.repo_url)
        artifact_dir = _artifact_dir(args.out, status.scanId)
        export_targets = _parse_export_formats(args.export)

        patch_result = None
        if args.finding_id and args.evidence_path:
            patch_result = patch_service.run_patch_blocking(status.scanId, args.finding_id, args.evidence_path, args.model)

        export_result = export_service.create_export(
            status.scanId,
            patch_id=patch_result.patchId if patch_result else None,
            formats=export_targets,
            output_dir=artifact_dir,
        )

        _print_run_result(status, report, patch_result, export_result, args.json, artifact_dir)
        return

    if args.command == "patch":
        result = patch_service.run_patch_blocking(args.scan_id, args.finding_id, args.evidence_path, args.model)
        artifact_dir = _artifact_dir(args.out, args.scan_id)
        export_result = export_service.create_export(
            args.scan_id,
            patch_id=result.patchId,
            formats=_parse_export_formats(args.export),
            output_dir=artifact_dir,
        )
        _print_patch_result(result, export_result, args.json, artifact_dir)
        return

    if args.command == "repair-patch":
        result = patch_service.repair_patch(args.scan_id, args.patch_id)
        artifact_dir = _artifact_dir(args.out, args.scan_id)
        export_result = export_service.create_export(
            args.scan_id,
            patch_id=result.patchId,
            formats=_parse_export_formats(args.export),
            output_dir=artifact_dir,
        )
        _print_patch_result(result, export_result, args.json, artifact_dir)
        return

    if args.command == "verify-patch":
        result = patch_service.verify_patch(args.scan_id, args.patch_id)
        _print_verification_result(result, args.json)
        return

    if args.command == "apply-patch":
        result = apply_service.apply_patch(args.scan_id, args.patch_id)
        _print_apply_result(result, args.json)
        return

    if args.command == "rollback-patch":
        result = apply_service.rollback_patch(args.apply_id)
        _print_apply_result(result, args.json)
        return

    if args.command == "github-review":
        artifact_dir = _artifact_dir(args.out, args.scan_id)
        review_result = github_review_service.create_review(
            args.scan_id,
            args.patch_id,
            repository=args.repo,
            pull_request_number=args.pr_number,
            post_comment=args.post,
            output_dir=artifact_dir,
        )
        _print_github_review_result(review_result, args.json, artifact_dir)
        return

    if args.command == "models":
        models = list_models()
        if args.json:
            print(json.dumps([item.model_dump(mode="json") for item in models], indent=2))
        else:
            for item in models:
                print(item.name)


def _artifact_dir(out: str | None, scan_id: str) -> Path:
    if out:
        artifact_dir = Path(out)
    else:
        artifact_dir = WORK_ROOT / "cli_exports" / scan_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


def _parse_export_formats(raw: str) -> set[str]:
    aliases = {
        "md": "markdown",
        "markdown": "markdown",
        "json": "json",
        "diff": "diff",
        "html": "html",
        "zip": "zip",
        "github": "github",
    }
    items = {aliases[item.strip().lower()] for item in raw.split(",") if item.strip().lower() in aliases}
    return items or {"json", "markdown", "html", "zip", "github"}


def _print_scan_result(
    status: ScanStatus,
    report: ScanReport,
    export_result: ExportResult,
    as_json: bool,
    artifact_dir: Path,
) -> None:
    payload = {
        "scan": status.model_dump(mode="json"),
        "report": report.model_dump(mode="json"),
        "export": export_result.model_dump(mode="json"),
        "artifactDir": str(artifact_dir),
    }
    if as_json:
        print(json.dumps(payload, indent=2))
        return

    print(f"Scan {status.scanId} completed for {report.repo.url}")
    print(f"Portability score: {report.summary.portabilityScore}")
    print(f"Bundle files: {len(export_result.files)}")
    print(f"Artifacts: {artifact_dir}")


def _print_patch_result(result: PatchResult, export_result: ExportResult, as_json: bool, artifact_dir: Path) -> None:
    payload = {
        "patch": result.model_dump(mode="json"),
        "export": export_result.model_dump(mode="json"),
        "artifactDir": str(artifact_dir),
    }
    if as_json:
        print(json.dumps(payload, indent=2))
        return

    print(f"Patch {result.patchId}: {result.status}")
    if result.savedPatchPath:
        print(f"Saved patch: {result.savedPatchPath}")
    if result.savedPatchedFilePath:
        print(f"Patched file snapshot: {result.savedPatchedFilePath}")
    if result.validation:
        print(f"Validation: {result.validation.state} via {result.validation.tool}")
    if result.riskAssessment:
        print(f"Risk: {result.riskAssessment.score}/100 ({result.riskAssessment.level})")
    if result.warnings:
        print(f"Warnings: {len(result.warnings)}")
    if result.error:
        print(f"Error: {result.error}")
    print(f"Bundle files: {len(export_result.files)}")


def _print_run_result(
    status: ScanStatus,
    report: ScanReport,
    patch_result: PatchResult | None,
    export_result: ExportResult,
    as_json: bool,
    artifact_dir: Path,
) -> None:
    payload = {
        "scan": status.model_dump(mode="json"),
        "report": report.model_dump(mode="json"),
        "patch": patch_result.model_dump(mode="json") if patch_result else None,
        "export": export_result.model_dump(mode="json"),
        "artifactDir": str(artifact_dir),
    }
    if as_json:
        print(json.dumps(payload, indent=2))
        return

    print(f"Run complete for {report.repo.url}")
    print(f"Scan ID: {status.scanId}")
    print(f"Score: {report.summary.portabilityScore}")
    if patch_result:
        print(f"Patch: {patch_result.status}")
        if patch_result.savedPatchPath:
            print(f"Patch file: {patch_result.savedPatchPath}")
        if patch_result.savedPatchedFilePath:
            print(f"Patched file snapshot: {patch_result.savedPatchedFilePath}")
        if patch_result.validation:
            print(f"Validation: {patch_result.validation.state} via {patch_result.validation.tool}")
        if patch_result.riskAssessment:
            print(f"Risk: {patch_result.riskAssessment.score}/100 ({patch_result.riskAssessment.level})")
        if patch_result.warnings:
            print(f"Warnings: {len(patch_result.warnings)}")
    print(f"Bundle files: {len(export_result.files)}")
    print(f"Artifacts: {artifact_dir}")


def _print_github_review_result(result: GitHubReviewResult, as_json: bool, artifact_dir: Path) -> None:
    payload = {
        "githubReview": result.model_dump(mode="json"),
        "artifactDir": str(artifact_dir),
    }
    if as_json:
        print(json.dumps(payload, indent=2))
        return

    print(f"GitHub review {result.reviewId} for {result.repository}")
    print(f"Risk: {result.riskScore}/100 ({result.riskLevel})")
    print(f"Markdown: {result.savedMarkdownPath}")
    print(f"JSON: {result.savedJsonPath}")
    print(f"Inline comments: {result.savedInlineCommentsPath} ({result.inlineCommentsCount})")
    if result.savedPrSafeInlineCommentsPath:
        print(f"PR-safe inline comments: {result.savedPrSafeInlineCommentsPath} ({result.prSafeInlineCommentsCount})")
    if result.posted and result.postUrl:
        print(f"Posted: {result.postUrl}")
    elif result.postError:
        print(f"Post warning: {result.postError}")


def _print_apply_result(result: PatchApplyResult, as_json: bool) -> None:
    payload = {"apply": result.model_dump(mode="json")}
    if as_json:
        print(json.dumps(payload, indent=2))
        return

    print(f"Apply {result.applyId}: {result.status}")
    print(f"Target: {result.targetFilePath}")
    print(f"Backup: {result.backupFilePath}")
    print(f"Applied snapshot: {result.appliedFilePath}")
    if result.error:
        print(f"Error: {result.error}")


def _print_verification_result(result: PatchVerificationReceipt, as_json: bool) -> None:
    payload = {"verification": result.model_dump(mode="json")}
    if as_json:
        print(json.dumps(payload, indent=2))
        return

    print(f"Verification {result.receiptId}: {result.state}")
    print(result.summary)
    print(f"Apply ready: {result.applyReady}")
    print(f"Export ready: {result.exportReady}")
    if result.savedReceiptPath:
        print(f"Receipt: {result.savedReceiptPath}")
    for check in result.checks:
        print(f"- {check.state}: {check.label} - {check.message}")


if __name__ == "__main__":
    main()
