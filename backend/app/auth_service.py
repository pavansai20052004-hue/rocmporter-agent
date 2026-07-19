"""Supabase JWT verification + plan lookup for backend enforcement.

Two verification paths, tried in order:

1. Local HS256 HMAC with SUPABASE_JWT_SECRET — free, but only works while the
   Supabase project signs access tokens with the legacy shared secret.
2. Remote verification via the Supabase Auth API (GET /auth/v1/user) — works
   for ANY signing algorithm (Supabase projects have migrated to asymmetric
   ES256 keys, which broke pure-HS256 verifiers). Verified tokens are cached
   in-memory for a few minutes so steady-state cost is ~one network hop per
   user per TTL window.

Enforcement is OPT-IN: it turns on when SUPABASE_JWT_SECRET or the
SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY pair is configured. With neither,
protected endpoints stay open (keeps local dev working).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request

from .env_config import load_local_env

load_local_env()

_TOKEN_CACHE: dict[str, tuple[dict, float]] = {}
_TOKEN_CACHE_LOCK = threading.Lock()
_TOKEN_CACHE_TTL_SECONDS = 300
_TOKEN_CACHE_MAX = 500


def enforcement_enabled() -> bool:
    if os.getenv("SUPABASE_JWT_SECRET"):
        return True
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _decode_segment(segment: str) -> dict | None:
    try:
        data = json.loads(_b64url_decode(segment))
    except (ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _verify_hs256(token: str, secret: str) -> dict | None:
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
    claims = _decode_segment(payload_b64)
    if claims is None:
        return None
    exp = claims.get("exp")
    if isinstance(exp, (int, float)) and exp < time.time():
        return None
    return claims


def _verify_via_auth_api(token: str) -> dict | None:
    """Ask Supabase itself whether the token is valid (algorithm-agnostic)."""
    base = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not (base and key):
        return None

    cache_id = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = time.time()
    with _TOKEN_CACHE_LOCK:
        hit = _TOKEN_CACHE.get(cache_id)
        if hit and hit[1] > now:
            return hit[0]

    request = urllib.request.Request(
        f"{base.rstrip('/')}/auth/v1/user",
        headers={"apikey": key.strip(), "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            user = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError):
        return None
    user_id = user.get("id") if isinstance(user, dict) else None
    if not user_id:
        return None

    claims = {"sub": user_id, "email": user.get("email"), "role": user.get("role", "authenticated")}
    payload = _decode_segment(token.split(".")[1]) if token.count(".") == 2 else None
    exp = (payload or {}).get("exp")
    cache_until = now + _TOKEN_CACHE_TTL_SECONDS
    if isinstance(exp, (int, float)):
        cache_until = min(cache_until, float(exp))
    with _TOKEN_CACHE_LOCK:
        if len(_TOKEN_CACHE) >= _TOKEN_CACHE_MAX:
            _TOKEN_CACHE.clear()
        _TOKEN_CACHE[cache_id] = (claims, cache_until)
    return claims


def verify_token(authorization: str | None) -> dict | None:
    """Return verified JWT claims, or None if missing/invalid/unverifiable."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    if token.count(".") != 2:
        return None

    header = _decode_segment(token.split(".")[0]) or {}
    secret = os.getenv("SUPABASE_JWT_SECRET")
    if secret and header.get("alg") == "HS256":
        claims = _verify_hs256(token, secret)
        if claims is not None:
            return claims
    # Non-HS256 algorithms (Supabase's ES256 keys) — or HS256 secret mismatch —
    # fall through to authoritative remote verification.
    return _verify_via_auth_api(token)


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
