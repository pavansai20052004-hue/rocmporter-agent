"""Stripe billing (checkout + webhook) using only the standard library.

Configure via environment variables:
    STRIPE_SECRET_KEY          sk_test_... (test mode) or sk_live_...
    STRIPE_PRICE_PRO           price_... for the Pro plan
    STRIPE_WEBHOOK_SECRET      whsec_... (optional, for webhook verification)

Keep these secret. On Render set them in the dashboard, never in git.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from .env_config import load_local_env

load_local_env()

STRIPE_API = "https://api.stripe.com/v1"

# plan -> env var holding the Stripe price id
_PLAN_PRICE_ENV = {
    "pro": "STRIPE_PRICE_PRO",
}


def is_configured() -> bool:
    return bool(os.getenv("STRIPE_SECRET_KEY"))


def _secret_key() -> str:
    key = os.getenv("STRIPE_SECRET_KEY")
    if not key:
        raise RuntimeError(
            "Billing is not configured. Set STRIPE_SECRET_KEY in the server environment to enable checkout."
        )
    return key.strip()


def _price_id(plan: str) -> str:
    env_name = _PLAN_PRICE_ENV.get(plan)
    if not env_name:
        raise ValueError(f"Plan '{plan}' is not available for self-serve checkout.")
    price = os.getenv(env_name)
    if not price:
        raise RuntimeError(f"Missing {env_name}. Add the Stripe price id for the {plan} plan.")
    return price.strip()


def create_checkout_session(
    plan: str,
    success_url: str,
    cancel_url: str,
    *,
    customer_email: str | None = None,
    client_reference_id: str | None = None,
) -> str:
    """Create a Stripe Checkout session and return its hosted URL."""
    price = _price_id(plan)
    form = {
        "mode": "subscription",
        "line_items[0][price]": price,
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "allow_promotion_codes": "true",
    }
    if customer_email:
        form["customer_email"] = customer_email
    if client_reference_id:
        form["client_reference_id"] = client_reference_id

    data = urllib.parse.urlencode(form).encode("utf-8")
    request = urllib.request.Request(
        f"{STRIPE_API}/checkout/sessions",
        data=data,
        headers={
            "Authorization": f"Bearer {_secret_key()}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")
        except Exception:  # pragma: no cover
            detail = exc.reason
        raise RuntimeError(f"Stripe checkout failed (HTTP {exc.code}): {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach Stripe: {getattr(exc, 'reason', exc)}") from exc

    url = payload.get("url")
    if not url:
        raise RuntimeError("Stripe did not return a checkout URL.")
    return url


def _supabase_configured() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))


def _patch_profile(filter_query: str, fields: dict) -> None:
    """Update the profiles table via the Supabase REST API using the service
    role key (bypasses RLS). No-op if Supabase isn't configured."""
    if not _supabase_configured():
        return
    base = os.getenv("SUPABASE_URL").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY").strip()
    url = f"{base}/rest/v1/profiles?{filter_query}"
    request = urllib.request.Request(
        url,
        data=json.dumps(fields).encode("utf-8"),
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        method="PATCH",
    )
    try:
        urllib.request.urlopen(request, timeout=20)
    except urllib.error.HTTPError as exc:  # pragma: no cover - best effort
        detail = ""
        try:
            detail = exc.read().decode("utf-8")
        except Exception:
            detail = exc.reason
        raise RuntimeError(f"Supabase profile update failed (HTTP {exc.code}): {detail[:200]}") from exc


def apply_subscription_event(event: dict) -> str | None:
    """Map a Stripe event to a plan change in the database. Returns a short
    status string for logging. Safe to call even if Supabase isn't set up."""
    etype = event.get("type")
    obj = event.get("data", {}).get("object", {})

    if etype == "checkout.session.completed":
        user_id = obj.get("client_reference_id")
        customer = obj.get("customer")
        if user_id:
            fields = {"plan": "pro"}
            if customer:
                fields["stripe_customer_id"] = customer
            _patch_profile(f"id=eq.{user_id}", fields)
            return f"upgraded {user_id} to pro"
        return "checkout completed without client_reference_id"

    if etype in ("customer.subscription.deleted", "customer.subscription.updated"):
        customer = obj.get("customer")
        status = obj.get("status", "")
        active = etype == "customer.subscription.updated" and status in ("active", "trialing")
        plan = "pro" if active else "free"
        if customer:
            _patch_profile(f"stripe_customer_id=eq.{customer}", {"plan": plan})
            return f"set customer {customer} to {plan}"
        return "subscription event without customer"

    return None


def verify_and_parse_webhook(payload: bytes, signature_header: str | None) -> dict:
    """Verify the Stripe-Signature header and return the parsed event.

    If STRIPE_WEBHOOK_SECRET is not set, the signature check is skipped (dev mode).
    """
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if secret and signature_header:
        _verify_signature(payload, signature_header, secret.strip())
    return json.loads(payload.decode("utf-8"))


def _verify_signature(payload: bytes, signature_header: str, secret: str) -> None:
    parts = dict(
        item.split("=", 1) for item in signature_header.split(",") if "=" in item
    )
    timestamp = parts.get("t")
    provided = parts.get("v1")
    if not timestamp or not provided:
        raise ValueError("Malformed Stripe-Signature header.")

    if abs(time.time() - int(timestamp)) > 300:
        raise ValueError("Stripe webhook timestamp outside tolerance.")

    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, provided):
        raise ValueError("Stripe webhook signature mismatch.")
