from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from .env_config import get_github_token
from .models import GitHubInlineComment, GitHubReviewResult, PatchResult, PatchVerificationReceipt, ScanReport
from .patch_service import patch_service
from .service import WORK_ROOT, scan_service


REVIEW_ROOT = WORK_ROOT / "github-reviews"
MAX_DIFF_LINES = 180
MAX_BODY_CHARS = 18_000


@dataclass(frozen=True)
class PullRequestFileDiff:
    filename: str
    previous_filename: str | None
    commentable_lines: frozenset[int]


class GitHubReviewService:
    def __init__(self) -> None:
        REVIEW_ROOT.mkdir(parents=True, exist_ok=True)

    def create_review(
        self,
        scan_id: str,
        patch_id: str,
        *,
        repository: str | None = None,
        pull_request_number: int | None = None,
        post_comment: bool = False,
        output_dir: Path | None = None,
    ) -> GitHubReviewResult:
        report = scan_service.get_report(scan_id)
        if report is None:
            raise ValueError("Scan report is not ready for GitHub review generation.")

        patch = patch_service.get_patch(patch_id)
        if patch is None or patch.scanId != scan_id:
            raise ValueError("Patch artifact was not found for this scan.")
        if patch.status != "completed":
            raise ValueError("Patch must complete before GitHub review generation.")

        verification = patch_service.verify_patch(scan_id, patch.patchId)
        if not verification.exportReady:
            raise ValueError(f"Patch verification is not export-ready: {verification.summary}")

        review_id = output_dir.name if output_dir is not None else f"review_{uuid.uuid4().hex[:10]}"
        root_dir = output_dir or (REVIEW_ROOT / scan_id / review_id)
        root_dir.mkdir(parents=True, exist_ok=True)

        repository_slug = repository or infer_repository_slug(report.repo.url)
        inline_comments = generate_inline_comments(report, patch)
        pr_safe_inline_comments: list[GitHubInlineComment] = []
        pr_diff_warning: str | None = None
        if pull_request_number is not None:
            pr_safe_inline_comments, pr_diff_warning = _filter_inline_comments_for_pull_request(
                repository_slug,
                pull_request_number,
                inline_comments,
            )

        comment_body = render_review_comment(report, patch, repository_slug, pull_request_number, inline_comments, verification)
        payload = build_review_payload(
            report,
            patch,
            verification,
            repository_slug,
            pull_request_number,
            comment_body,
            inline_comments,
            pr_safe_inline_comments,
            pr_diff_warning,
        )

        markdown_path = root_dir / "github-review.md"
        json_path = root_dir / "github-review.json"
        inline_path = root_dir / "github-inline-comments.json"
        pr_safe_inline_path = root_dir / "github-inline-comments-pr-safe.json" if pull_request_number is not None else None

        markdown_path.write_text(comment_body, encoding="utf-8")
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        inline_path.write_text(json.dumps([item.model_dump(mode="json") for item in inline_comments], indent=2), encoding="utf-8")
        if pr_safe_inline_path is not None:
            pr_safe_inline_path.write_text(
                json.dumps([item.model_dump(mode="json") for item in pr_safe_inline_comments], indent=2),
                encoding="utf-8",
            )

        posted = False
        post_url = None
        post_error = None
        if post_comment:
            if not verification.exportReady:
                post_error = "GitHub posting blocked because patch verification is not export-ready."
            elif pull_request_number is None:
                post_error = "A pull request number is required before posting a GitHub comment."
            else:
                post_url, post_error = _post_review(repository_slug, pull_request_number, comment_body, pr_safe_inline_comments)
                posted = post_url is not None
                if posted and post_error is None and pr_diff_warning and inline_comments and not pr_safe_inline_comments:
                    post_error = f"Posted summary comment only: {pr_diff_warning}"

        return GitHubReviewResult(
            reviewId=review_id,
            scanId=scan_id,
            patchId=patch.patchId,
            repository=repository_slug,
            pullRequestNumber=pull_request_number,
            createdAt=datetime.now(UTC),
            verificationState=verification.state,
            applyReady=verification.applyReady,
            exportReady=verification.exportReady,
            reviewReady=verification.exportReady,
            draftOnly=not verification.exportReady,
            riskScore=patch.riskAssessment.score if patch.riskAssessment else 50,
            riskLevel=patch.riskAssessment.level if patch.riskAssessment else "medium",
            summary=_review_summary(patch, verification),
            warnings=payload["warnings"],
            commentBody=comment_body,
            savedMarkdownPath=str(markdown_path.resolve()),
            savedJsonPath=str(json_path.resolve()),
            savedInlineCommentsPath=str(inline_path.resolve()),
            inlineCommentsCount=len(inline_comments),
            savedPrSafeInlineCommentsPath=str(pr_safe_inline_path.resolve()) if pr_safe_inline_path is not None else None,
            prSafeInlineCommentsCount=len(pr_safe_inline_comments),
            posted=posted,
            postUrl=post_url,
            postError=post_error,
        )


def build_review_payload(
    report: ScanReport,
    patch: PatchResult,
    verification: PatchVerificationReceipt | None,
    repository: str | None,
    pull_request_number: int | None,
    comment_body: str,
    inline_comments: list[GitHubInlineComment],
    pr_safe_inline_comments: list[GitHubInlineComment] | None = None,
    pr_diff_warning: str | None = None,
) -> dict:
    finding = next((item for item in report.findings if item.id == patch.findingId), None)
    warnings = [item.message for item in patch.warnings]
    if verification is not None and not verification.exportReady:
        warnings.append("Draft-only review: patch verification is not export-ready, so GitHub posting is blocked.")
    elif verification is not None and not verification.applyReady:
        warnings.append("Workspace apply is blocked by verification; use this as a review/export artifact.")
    if pr_diff_warning:
        warnings.append(pr_diff_warning)

    return {
        "repository": repository,
        "pullRequestNumber": pull_request_number,
        "scanId": patch.scanId,
        "patchId": patch.patchId,
        "findingId": patch.findingId,
        "targetFile": patch.evidencePath,
        "portabilityScore": report.summary.portabilityScore,
        "patchRisk": patch.riskAssessment.model_dump(mode="json") if patch.riskAssessment else None,
        "verification": verification.model_dump(mode="json") if verification else None,
        "applyReady": bool(verification.applyReady) if verification else False,
        "exportReady": bool(verification.exportReady) if verification else False,
        "reviewReady": bool(verification.exportReady) if verification else False,
        "draftOnly": not bool(verification.exportReady) if verification else True,
        "warnings": warnings,
        "validation": patch.validation.model_dump(mode="json") if patch.validation else None,
        "inlineComments": [item.model_dump(mode="json") for item in inline_comments],
        "prSafeInlineComments": [item.model_dump(mode="json") for item in pr_safe_inline_comments or []],
        "prDiffWarning": pr_diff_warning,
        "commentBody": comment_body,
        "generatedAt": datetime.now(UTC).isoformat(),
        "finding": finding.model_dump(mode="json") if finding else None,
    }


def render_review_comment(
    report: ScanReport,
    patch: PatchResult,
    repository: str | None,
    pull_request_number: int | None,
    inline_comments: list[GitHubInlineComment] | None = None,
    verification: PatchVerificationReceipt | None = None,
) -> str:
    finding = next((item for item in report.findings if item.id == patch.findingId), None)
    top_findings = report.findings[:3]
    risk = patch.riskAssessment
    diff_preview = _truncate_diff(patch.diff or "")
    comment_suggestions = inline_comments if inline_comments is not None else generate_inline_comments(report, patch)
    draft_only = verification is not None and not verification.exportReady

    lines = [
        f"## ROCmPorter {'Draft Review' if draft_only else 'Review'} for `{repository or report.repo.name}`",
        "",
        f"- Scan ID: `{patch.scanId}`",
        f"- PR: `{f'#{pull_request_number}' if pull_request_number else 'not specified'}`",
        f"- Portability score: `{report.summary.portabilityScore}`",
        f"- Patch target: `{patch.evidencePath}`",
        f"- Patch status: `{patch.status}` via `{patch.model}`",
    ]

    if verification is not None:
        lines.extend(
            [
                f"- Verification state: `{verification.state}`",
                f"- Export ready: `{verification.exportReady}`",
                f"- Apply ready: `{verification.applyReady}`",
            ]
        )
        if not verification.exportReady:
            lines.extend(
                [
                    "",
                    "> Draft only: verification is not export-ready, so this comment must not be posted to a pull request yet.",
                ]
            )
        elif not verification.applyReady:
            lines.extend(
                [
                    "",
                    "> Review artifact: export is ready, but workspace apply remains blocked by verification.",
                ]
            )

    if risk is not None:
        lines.append(f"- Patch review risk: `{risk.score}/100` ({risk.level})")

    lines.extend(
        [
            "",
            "### What this patch is trying to fix",
            f"- Finding: `{patch.findingId}`",
            f"- Title: {finding.title if finding else patch.findingId}",
            f"- Recommendation: {finding.recommendation if finding else 'Review the matching ROCm migration finding.'}",
        ]
    )

    if risk is not None:
        lines.extend(["", "### Why this still needs review"])
        for reason in risk.reasons:
            lines.append(f"- {reason}")

    if patch.warnings:
        lines.extend(["", "### Warnings"])
        for warning in patch.warnings:
            lines.append(f"- `{warning.severity}` {warning.message}")

    if patch.validation is not None:
        lines.extend(
            [
                "",
                "### Local validation",
                f"- State: `{patch.validation.state}`",
                f"- Tool: `{patch.validation.tool}`",
                f"- Summary: {patch.validation.summary}",
            ]
        )

    lines.extend(["", "### Broader repository context"])
    for item in top_findings:
        lines.append(f"- `{item.severity}` {item.title}")

    if risk is not None and risk.checklist:
        lines.extend(["", "### Review checklist"])
        for item in risk.checklist:
            lines.append(f"- [ ] {item}")

    if comment_suggestions:
        lines.extend(["", "### Inline review suggestions"])
        for item in comment_suggestions[:4]:
            lines.append(f"- `{item.path}:{item.line}` {item.body}")

    if patch.rationale:
        lines.extend(["", "### Model rationale", patch.rationale])

    lines.extend(["", "### Suggested patch", "```diff", diff_preview, "```"])

    if patch.diff and diff_preview != patch.diff:
        lines.append("_Diff preview truncated for comment size. Use the saved artifact for the full patch._")

    body = "\n".join(lines).strip() + "\n"
    if len(body) <= MAX_BODY_CHARS:
        return body

    trimmed = lines[:]
    while len("\n".join(trimmed).strip()) > MAX_BODY_CHARS and len(trimmed) > 12:
        trimmed.pop(-5)
    return "\n".join(trimmed).strip() + "\n"


def _truncate_diff(diff_text: str) -> str:
    lines = diff_text.splitlines()
    if len(lines) <= MAX_DIFF_LINES:
        return diff_text.strip()
    visible = lines[:MAX_DIFF_LINES]
    visible.append("... diff truncated ...")
    return "\n".join(visible)


def _review_summary(patch: PatchResult, verification: PatchVerificationReceipt) -> str:
    if not verification.exportReady:
        return f"Draft review only: {verification.summary}"
    if not verification.applyReady:
        return f"Export-ready review artifact; workspace apply remains blocked. {patch.riskAssessment.summary if patch.riskAssessment else verification.summary}"
    return patch.riskAssessment.summary if patch.riskAssessment else "Patch verification passed for export and workspace apply."


def generate_inline_comments(report: ScanReport, patch: PatchResult) -> list[GitHubInlineComment]:
    finding = next((item for item in report.findings if item.id == patch.findingId), None)
    evidence = None if finding is None else next((item for item in finding.evidence if item.path == patch.evidencePath), None)
    if finding is None or evidence is None:
        return []

    patched_text = _read_patched_text(patch)
    comments: list[GitHubInlineComment] = []

    def add_comment(path: str, line: int, body: str, severity: str, source: str, code: str) -> None:
        if any(item.path == path and item.line == line and item.code == code for item in comments):
            return
        comments.append(
            GitHubInlineComment(
                path=path,
                line=max(1, line),
                body=body,
                severity=severity,
                source=source,
                code=code,
            )
        )

    if evidence.lineStart is not None:
        add_comment(
            evidence.path,
            evidence.lineStart,
            f"ROCmPorter flagged `{finding.id}` here. Verify the local patch actually resolves this CUDA-specific assumption.",
            finding.severity,
            "evidence",
            "evidence_anchor",
        )

    for warning in patch.warnings:
        line = _line_for_warning(warning.code, patched_text, evidence)
        add_comment(
            evidence.path,
            line,
            warning.message,
            warning.severity,
            "warning",
            warning.code,
        )

    if patch.riskAssessment:
        for factor in patch.riskAssessment.factors[:3]:
            if factor.code in {item.code for item in comments}:
                continue
            line = _line_for_factor(factor.code, patched_text, evidence)
            add_comment(
                evidence.path,
                line,
                factor.detail,
                "medium" if factor.points < 18 else "high",
                "risk",
                factor.code,
            )

    return comments[:6]


def infer_repository_slug(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    if parsed.netloc.lower() != "github.com":
        raise ValueError("GitHub review automation currently supports GitHub repository URLs only.")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError("Could not infer owner and repository from the provided GitHub URL.")
    return f"{parts[0]}/{parts[1].removesuffix('.git')}"


def _post_review(
    repository: str,
    pull_request_number: int,
    body: str,
    inline_comments: list[GitHubInlineComment],
) -> tuple[str | None, str | None]:
    token = get_github_token()
    if not token:
        return None, "No GitHub token was configured on the backend process."

    if inline_comments:
        review_url, review_error = _post_pull_review(repository, pull_request_number, body, inline_comments, token)
        if review_url is not None:
            return review_url, None
        summary_url, summary_error = _post_issue_comment(repository, pull_request_number, body, token)
        if summary_url is not None:
            combined_error = f"Inline review post fell back to summary comment: {review_error}"
            return summary_url, combined_error
        return None, review_error or summary_error

    return _post_issue_comment(repository, pull_request_number, body, token)


def _post_issue_comment(repository: str, pull_request_number: int, body: str, token: str) -> tuple[str | None, str | None]:
    payload = json.dumps({"body": body}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/issues/{pull_request_number}/comments",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="ignore")
        return None, f"GitHub comment post failed: {exc.code} {message or exc.reason}"
    except urllib.error.URLError as exc:
        return None, f"GitHub comment post failed: {exc.reason}"

    return data.get("html_url"), None


def _post_pull_review(
    repository: str,
    pull_request_number: int,
    body: str,
    inline_comments: list[GitHubInlineComment],
    token: str,
) -> tuple[str | None, str | None]:
    pull_request = _github_get_json(f"https://api.github.com/repos/{repository}/pulls/{pull_request_number}", token)
    if pull_request is None:
        return None, "Unable to fetch pull request details for inline review posting."

    commit_id = pull_request.get("head", {}).get("sha")
    if not commit_id:
        return None, "Pull request head SHA is missing, so inline review comments cannot be posted."

    payload = {
        "body": body,
        "event": "COMMENT",
        "commit_id": commit_id,
        "comments": [
            {
                "path": item.path,
                "line": item.line,
                "side": item.side,
                "body": item.body,
            }
            for item in inline_comments
        ],
    }
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/pulls/{pull_request_number}/reviews",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="ignore")
        return None, f"GitHub inline review post failed: {exc.code} {message or exc.reason}"
    except urllib.error.URLError as exc:
        return None, f"GitHub inline review post failed: {exc.reason}"

    return data.get("html_url"), None


def _filter_inline_comments_for_pull_request(
    repository: str,
    pull_request_number: int,
    inline_comments: list[GitHubInlineComment],
) -> tuple[list[GitHubInlineComment], str | None]:
    if not inline_comments:
        return [], None

    pr_files = _github_get_pull_request_files(repository, pull_request_number, get_github_token())
    if pr_files is None:
        return [], "Unable to verify the current PR diff for inline review comments. GitHub posting will fall back to a summary comment."

    aliases = _build_pr_file_alias_map(pr_files)
    filtered: list[GitHubInlineComment] = []
    dropped = 0

    for comment in inline_comments:
        pr_file = aliases.get(comment.path)
        if pr_file is None or comment.line not in pr_file.commentable_lines:
            dropped += 1
            continue
        if comment.path != pr_file.filename:
            filtered.append(comment.model_copy(update={"path": pr_file.filename}))
            continue
        filtered.append(comment)

    if not filtered:
        return [], "No inline review suggestions matched the current PR diff, so GitHub posting can only use the summary comment."

    if dropped:
        return filtered, f"Filtered {dropped} inline review suggestion(s) that were outside the current PR diff."

    return filtered, None


def _github_get_pull_request_files(
    repository: str,
    pull_request_number: int,
    token: str | None,
) -> list[PullRequestFileDiff] | None:
    items = _github_get_paginated_json(
        f"https://api.github.com/repos/{repository}/pulls/{pull_request_number}/files",
        token,
    )
    if items is None:
        return None

    diffs: list[PullRequestFileDiff] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename")
        if not isinstance(filename, str) or not filename:
            continue
        previous_filename = item.get("previous_filename")
        patch_text = item.get("patch")
        commentable_lines = frozenset(_parse_commentable_lines(patch_text if isinstance(patch_text, str) else ""))
        diffs.append(
            PullRequestFileDiff(
                filename=filename,
                previous_filename=previous_filename if isinstance(previous_filename, str) else None,
                commentable_lines=commentable_lines,
            )
        )
    return diffs


def _build_pr_file_alias_map(pr_files: list[PullRequestFileDiff]) -> dict[str, PullRequestFileDiff]:
    aliases: dict[str, PullRequestFileDiff] = {}
    for item in pr_files:
        aliases[item.filename] = item
        if item.previous_filename:
            aliases.setdefault(item.previous_filename, item)
    return aliases


def _github_get_paginated_json(url: str, token: str | None) -> list[dict] | None:
    results: list[dict] = []
    page = 1
    per_page = 100

    while True:
        page_url = f"{url}{'&' if '?' in url else '?'}per_page={per_page}&page={page}"
        data = _github_get_json(page_url, token)
        if data is None:
            return None if page == 1 else results
        if not isinstance(data, list):
            return None

        results.extend(item for item in data if isinstance(item, dict))
        if len(data) < per_page:
            return results
        page += 1


def _github_get_json(url: str, token: str | None) -> dict | list[dict] | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        url,
        headers=headers,
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError):
        return None


def _parse_commentable_lines(patch_text: str) -> set[int]:
    commentable: set[int] = set()
    new_line = 0
    in_hunk = False

    for line in patch_text.splitlines():
        if line.startswith("@@"):
            new_line = _parse_new_file_hunk_start(line)
            in_hunk = new_line > 0
            continue
        if not in_hunk or line.startswith("\\"):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            commentable.add(new_line)
            new_line += 1
            continue
        if line.startswith(" "):
            commentable.add(new_line)
            new_line += 1
            continue
        if line.startswith("-") and not line.startswith("---"):
            continue

    return commentable


def _parse_new_file_hunk_start(header_line: str) -> int:
    for chunk in header_line.split():
        if chunk.startswith("+"):
            start_text = chunk[1:].split(",", maxsplit=1)[0]
            try:
                return max(0, int(start_text))
            except ValueError:
                return 0
    return 0


def _read_patched_text(patch: PatchResult) -> str:
    if patch.savedPatchedFilePath:
        path = Path(patch.savedPatchedFilePath)
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore")
    return ""


def _line_for_warning(code: str, patched_text: str, evidence) -> int:
    token_map = {
        "response_artifact_leak": "needsMoreContext=",
        "change_outside_evidence_window": evidence.matchText or "",
        "destructive_line_removal": evidence.matchText or "",
    }
    token = token_map.get(code, "") if patched_text else ""
    return _find_line_for_token(patched_text, token) or evidence.lineStart or 1


def _line_for_factor(code: str, patched_text: str, evidence) -> int:
    token_map = {
        "residual_cuda_build_markers": "CUDAExtension",
        "mixed_build_toolchain": "hipcc",
        "residual_cuda_runtime": "cuda_runtime.h",
        "residual_cuda_api": "torch.cuda",
        "no_hip_signal": evidence.matchText or "",
        "narrow_hip_swap": "hipcc",
        "multi_hunk_edit": evidence.matchText or "",
    }
    token = token_map.get(code, "")
    return _find_line_for_token(patched_text, token) or evidence.lineStart or 1


def _find_line_for_token(text: str, token: str) -> int | None:
    if not text or not token:
        return None
    for index, line in enumerate(text.splitlines(), start=1):
        if token.lower() in line.lower():
            return index
    return None


github_review_service = GitHubReviewService()
