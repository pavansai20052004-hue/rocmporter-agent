"""Razorpay billing (India-friendly real payments).

Model: one-time payment that grants Pro for 31 days (no recurring e-mandate
complexity). The frontend opens Razorpay Checkout with an order created here;
after payment we verify the HMAC signature server-side and upgrade the user's
plan with an expiry (`profiles.pro_until`).

Environment:
    RAZORPAY_KEY_ID        rzp_test_... or rzp_live_...
    RAZORPAY_KEY_SECRET    the matching secret (server-side only)
    RAZORPAY_AMOUNT_PAISE  price of Pro in paise (default 249900 = Rs 2,499)
    PAYMENT_PROVIDER       optional override: 'razorpay' | 'stripe'
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

from .billing_service import _patch_profile, _supabase_configured
from .env_config import load_local_env

load_local_env()

RAZORPAY_API = "https://api.razorpay.com/v1"
PRO_DAYS = 31


def razorpay_configured() -> bool:
    return bool(os.getenv("RAZORPAY_KEY_ID") and os.getenv("RAZORPAY_KEY_SECRET"))


def active_provider() -> str:
    override = (os.getenv("PAYMENT_PROVIDER") or "").strip().lower()
    if override in ("razorpay", "stripe"):
        return override
    return "razorpay" if razorpay_configured() else "stripe"


def amount_paise() -> int:
    return max(100, int(os.getenv("RAZORPAY_AMOUNT_PAISE", "249900")))


def _auth_header() -> str:
    creds = f"{os.getenv('RAZORPAY_KEY_ID').strip()}:{os.getenv('RAZORPAY_KEY_SECRET').strip()}"
    return "Basic " + base64.b64encode(creds.encode("utf-8")).decode("ascii")


def create_order(user_id: str) -> dict:
    if not razorpay_configured():
        raise RuntimeError("Razorpay is not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET on the server.")
    body = {
        "amount": amount_paise(),
        "currency": "INR",
        "receipt": f"pro-{user_id[:24]}",
        "notes": {"user_id": user_id, "plan": "pro"},
    }
    request = urllib.request.Request(
        f"{RAZORPAY_API}/orders",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": _auth_header(), "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            order = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("description", "")
        except Exception:  # pragma: no cover
            pass
        raise RuntimeError(f"Razorpay order failed ({exc.code}): {detail[:200]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach Razorpay: {getattr(exc, 'reason', exc)}") from exc

    return {
        "provider": "razorpay",
        "orderId": order["id"],
        "keyId": os.getenv("RAZORPAY_KEY_ID").strip(),
        "amount": order["amount"],
        "currency": order.get("currency", "INR"),
    }


def verify_and_grant(user_id: str, order_id: str, payment_id: str, signature: str) -> str:
    """Verify Razorpay's payment signature and grant Pro. Returns pro_until ISO."""
    secret = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
    if not secret:
        raise RuntimeError("Razorpay is not configured on the server.")
    expected = hmac.new(secret.encode("utf-8"), f"{order_id}|{payment_id}".encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.strip()):
        raise ValueError("Payment signature verification failed. If you were charged, contact support.")

    pro_until = (datetime.now(UTC) + timedelta(days=PRO_DAYS)).isoformat()
    _patch_profile(f"id=eq.{user_id}", {"plan": "pro", "pro_until": pro_until})
    _record_payment(user_id, payment_id)
    return pro_until


def _record_payment(user_id: str, payment_ref: str) -> None:
    """Best-effort payment history row (table may not exist yet)."""
    if not _supabase_configured():
        return
    base = os.getenv("SUPABASE_URL").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY").strip()
    request = urllib.request.Request(
        f"{base}/rest/v1/payments",
        data=json.dumps(
            {
                "user_id": user_id,
                "provider": "razorpay",
                "amount": amount_paise(),
                "currency": "INR",
                "payment_ref": payment_ref,
                "status": "paid",
            }
        ).encode("utf-8"),
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(request, timeout=15)
    except urllib.error.URLError:
        pass  # history is non-critical
