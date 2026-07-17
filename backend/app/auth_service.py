"""Supabase JWT verification + plan lookup for backend enforcement.

Supabase issues HS256 JWTs signed with the project's JWT secret. We verify the
signature and expiry, then read the user's plan from the profiles table using
the service-role key.

Enforcement is OPT-IN: if SUPABASE_JWT_SECRET is not set, verification is
disabled and protected endpoints stay open (keeps local dev and the pre-auth
deployment working). Set SUPABASE_JWT_SECRET on the server to turn it on.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request

from .env_config import load_local_env

load_local_env()


def enforcement_enabled() -> bool:
    return bool(os.getenv("SUPABASE_JWT_SECRET"))


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def verify_token(authorization: str | None) -> dict | None:
    """Return verified JWT claims, or None if missing/invalid/unverifiable."""
    secret = os.getenv("SUPABASE_JWT_SECRET")
    if not secret or not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    parts = token.split(".")
    if len(parts) != 3:
        return None
    header_b64, payload_b64, signature_b64 = parts

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected = (
        base64.urlsafe_b64encode(hmac.new(secret.strip().encode("utf-8"), signing_input, hashlib.sha256).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    if not hmac.compare_digest(expected, signature_b64):
        return None

    try:
        claims = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None

    exp = claims.get("exp")
    if isinstance(exp, (int, float)) and exp < time.time():
        return None
    return claims


def get_user_plan(user_id: str | None) -> str:
    """Read the user's plan from Supabase, honoring pro_until expiry."""
    base = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not (base and key and user_id):
        return "free"
    url = f"{base.rstrip('/')}/rest/v1/profiles?id=eq.{user_id}&select=plan,pro_until"
    request = urllib.request.Request(
        url,
        headers={"apikey": key.strip(), "Authorization": f"Bearer {key.strip()}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            rows = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError):
        return "free"
    if not (isinstance(rows, list) and rows and isinstance(rows[0], dict)):
        return "free"
    plan = rows[0].get("plan") or "free"
    pro_until = rows[0].get("pro_until")
    if plan in ("pro", "team") and pro_until:
        try:
            expiry = datetime_fromiso(pro_until)
            if expiry < time.time():
                return "free"
        except ValueError:
            pass
    return plan


def datetime_fromiso(value: str) -> float:
    """ISO timestamp -> unix seconds (handles the trailing Z variant)."""
    from datetime import datetime

    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def is_pro_plan(plan: str) -> bool:
    return plan in ("pro", "team")


def delete_user(user_id: str) -> None:
    """Permanently delete a user via the Supabase Admin API. Cascades to the
    user's profiles/scans/payments rows (ON DELETE CASCADE)."""
    base = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not (base and key and user_id):
        raise RuntimeError("Account deletion is not available — the server is missing Supabase admin credentials.")
    request = urllib.request.Request(
        f"{base.rstrip('/')}/auth/v1/admin/users/{user_id}",
        headers={"apikey": key.strip(), "Authorization": f"Bearer {key.strip()}"},
        method="DELETE",
    )
    try:
        urllib.request.urlopen(request, timeout=20)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")
        except Exception:  # pragma: no cover
            pass
        raise RuntimeError(f"Could not delete account ({exc.code}): {detail[:160]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach Supabase: {getattr(exc, 'reason', exc)}") from exc
