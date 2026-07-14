from __future__ import annotations

import base64
import binascii
import json
import os

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import auth_service
from .rate_limit import RateLimiter
from .billing_service import (
    apply_subscription_event,
    create_checkout_session,
    create_portal_session,
    get_stripe_customer_id,
    verify_and_parse_webhook,
)

from .apply_service import apply_service
from .env_config import load_local_env
from .export_service import export_service
from .github_review_service import github_review_service
from .models import (
    BillingCheckoutRequest,
    BillingPortalRequest,
    ExportRequest,
    ExportResult,
    GitHubReviewRequest,
    GitHubReviewResult,
    OllamaHealthStatus,
    OllamaModelInfo,
    OllamaWarmRequest,
    PatchApplyRequest,
    PatchApplyResult,
    PatchRequest,
    PatchResult,
    PatchVerificationReceipt,
    ScanReport,
    ScanRequest,
    ScanStatus,
)
from .llm_service import get_health_status, list_models, warm_model
from .patch_service import patch_service
from .service import scan_service


load_local_env()
app = FastAPI(title="ROCmPorter Agent API", version="0.1.0")

cors_origins = os.getenv("APP_CORS_ORIGINS", "http://localhost:5178,http://127.0.0.1:5178")
cors_origin_regex = os.getenv(
    "APP_CORS_ALLOW_ORIGIN_REGEX",
    r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"
    r"|https://([a-z0-9-]+\.)*vercel\.app$",
)
allow_origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


scan_limiter = RateLimiter(
    max_requests=int(os.getenv("SCAN_RATE_LIMIT", "20")),
    window_seconds=int(os.getenv("SCAN_RATE_WINDOW_SECONDS", "3600")),
)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.get("/api/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": "rocmporter-agent", "version": app.version}


def require_pro_plan(authorization: str | None) -> None:
    """Backstop enforcement for paid features. No-op unless SUPABASE_JWT_SECRET
    is configured, so scanning and local dev stay open."""
    if not auth_service.enforcement_enabled():
        return
    claims = auth_service.verify_token(authorization)
    if not claims:
        raise HTTPException(status_code=401, detail="Please sign in to generate AI patches.")
    plan = auth_service.get_user_plan(claims.get("sub"))
    if not auth_service.is_pro_plan(plan):
        raise HTTPException(status_code=402, detail="AI patch generation requires a Pro plan. Upgrade to continue.")


@app.post("/api/scans", response_model=ScanStatus)
def create_scan(payload: ScanRequest, request: Request) -> ScanStatus:
    if not scan_limiter.allow(_client_ip(request)):
        raise HTTPException(
            status_code=429,
            detail="Too many scans from your network recently. Please wait a little and try again.",
        )
    try:
        return scan_service.create_scan(payload.repoUrl)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/scans/{scan_id}", response_model=ScanStatus)
def get_scan(scan_id: str) -> ScanStatus:
    scan = scan_service.get_scan(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan


@app.get("/api/scans/{scan_id}/report", response_model=ScanReport)
def get_report(scan_id: str) -> ScanReport:
    report = scan_service.get_report(scan_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not ready")
    return report


@app.get("/api/ollama/models", response_model=list[OllamaModelInfo])
def get_ollama_models() -> list[OllamaModelInfo]:
    try:
        return list_models()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/ollama/status", response_model=OllamaHealthStatus)
def get_ollama_status(model: str | None = None) -> OllamaHealthStatus:
    return get_health_status(model)


@app.post("/api/ollama/warm", response_model=OllamaHealthStatus)
def warm_ollama_model(payload: OllamaWarmRequest) -> OllamaHealthStatus:
    try:
        return warm_model(payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/scans/{scan_id}/patches", response_model=PatchResult)
def create_patch(
    scan_id: str,
    payload: PatchRequest,
    authorization: str | None = Header(default=None),
) -> PatchResult:
    require_pro_plan(authorization)
    try:
        return patch_service.create_patch(scan_id, payload.findingId, payload.evidencePath, payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/scans/{scan_id}/patches", response_model=list[PatchResult])
def list_scan_patches(scan_id: str) -> list[PatchResult]:
    return patch_service.list_patches(scan_id)


@app.get("/api/scans/{scan_id}/patches/{patch_id}", response_model=PatchResult)
def get_patch(scan_id: str, patch_id: str) -> PatchResult:
    result = patch_service.get_patch(patch_id)
    if result is None or result.scanId != scan_id:
        raise HTTPException(status_code=404, detail="Patch job not found")
    return result


@app.post("/api/scans/{scan_id}/patches/{patch_id}/repair", response_model=PatchResult)
def repair_patch(
    scan_id: str,
    patch_id: str,
    authorization: str | None = Header(default=None),
) -> PatchResult:
    require_pro_plan(authorization)
    try:
        return patch_service.repair_patch(scan_id, patch_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/scans/{scan_id}/patches/{patch_id}/verify", response_model=PatchVerificationReceipt)
def verify_patch(scan_id: str, patch_id: str) -> PatchVerificationReceipt:
    try:
        return patch_service.verify_patch(scan_id, patch_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/scans/{scan_id}/apply-patch", response_model=PatchApplyResult)
def apply_patch(scan_id: str, payload: PatchApplyRequest) -> PatchApplyResult:
    try:
        return apply_service.apply_patch(scan_id, payload.patchId)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/patch-applies/{apply_id}", response_model=PatchApplyResult)
def get_patch_apply(apply_id: str) -> PatchApplyResult:
    result = apply_service.get_apply(apply_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Applied patch record not found")
    return result


@app.post("/api/patch-applies/{apply_id}/rollback", response_model=PatchApplyResult)
def rollback_patch_apply(apply_id: str) -> PatchApplyResult:
    try:
        return apply_service.rollback_patch(apply_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/scans/{scan_id}/exports", response_model=ExportResult)
def create_export(scan_id: str, payload: ExportRequest) -> ExportResult:
    try:
        return export_service.create_export(
            scan_id,
            patch_id=payload.patchId,
            formats=set(payload.formats),
            expose_downloads=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/scans/{scan_id}/github-review", response_model=GitHubReviewResult)
def create_github_review(scan_id: str, payload: GitHubReviewRequest) -> GitHubReviewResult:
    try:
        return github_review_service.create_review(
            scan_id,
            payload.patchId,
            repository=payload.repository,
            pull_request_number=payload.pullRequestNumber,
            post_comment=payload.postComment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _identity_from_bearer(authorization: str | None) -> tuple[str | None, str | None]:
    """Best-effort read of email + user id from a Supabase JWT for checkout
    prefill. Not a security check — Stripe handles payment auth."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None, None
    token = authorization.split(" ", 1)[1].strip()
    segments = token.split(".")
    if len(segments) < 2:
        return None, None
    payload_segment = segments[1]
    padding = "=" * (-len(payload_segment) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_segment + padding)
        claims = json.loads(decoded.decode("utf-8"))
    except (binascii.Error, ValueError):
        return None, None
    return claims.get("email"), claims.get("sub")


@app.post("/api/billing/checkout")
def billing_checkout(
    payload: BillingCheckoutRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    email, user_id = _identity_from_bearer(authorization)
    try:
        url = create_checkout_session(
            payload.plan,
            payload.successUrl,
            payload.cancelUrl,
            customer_email=email,
            client_reference_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"url": url}


@app.post("/api/billing/portal")
def billing_portal(
    payload: BillingPortalRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    claims = auth_service.verify_token(authorization)
    if not claims:
        raise HTTPException(status_code=401, detail="Please sign in to manage your subscription.")
    customer_id = get_stripe_customer_id(claims.get("sub"))
    if not customer_id:
        raise HTTPException(status_code=400, detail="No active subscription found for this account.")
    try:
        url = create_portal_session(customer_id, payload.returnUrl)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"url": url}


@app.post("/api/billing/webhook")
async def billing_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, object]:
    body = await request.body()
    try:
        event = verify_and_parse_webhook(body, stripe_signature)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Map subscription lifecycle events to the user's plan in the database.
    try:
        status = apply_subscription_event(event)
    except RuntimeError:
        # Don't fail the webhook on a transient DB error; Stripe will retry.
        status = "db update failed"
    return {"received": True, "type": event.get("type"), "status": status}


@app.get("/api/scans/{scan_id}/exports/{export_id}/download/{relative_path:path}")
def download_export_file(scan_id: str, export_id: str, relative_path: str) -> FileResponse:
    try:
        path = export_service.resolve_export_file(scan_id, export_id, relative_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name)
