"""Payment adapter for the pharmacy module (cash / UPI-QR / Razorpay).

Kept in its own file so the checkout router does not have to know which
gateway is configured.

Two providers are supported and neither needs a third party package:

* **simulated** (default) - the patient scans the UPI QR shown on the order
  page, and the app marks the order paid. This is what the existing
  appointment flow in this project already does, so the pharmacy behaves the
  same way out of the box, offline, on a demo database.

* **Razorpay** - as soon as RAZORPAY_KEY_ID + RAZORPAY_KEY_SECRET are in .env,
  the same "pay" button opens Razorpay Checkout and the order is only
  confirmed when the HMAC-SHA256 signature of
  ``order_id|payment_id`` matches. Without a verified signature the order
  stays PENDING_PAYMENT, so nobody can mark an order paid by hand-typing a
  request.

Secrets are only ever read from the environment - never stored on a row,
never returned to the browser.
"""

import hashlib
import hmac
import logging
import os
import re
from uuid import uuid4

logger = logging.getLogger(__name__)


# =========================================================
# CONFIG
# =========================================================

def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def razorpay_key_id() -> str:
    return _env("RAZORPAY_KEY_ID")


def razorpay_key_secret() -> str:
    return _env("RAZORPAY_KEY_SECRET")


def razorpay_enabled() -> bool:
    return bool(razorpay_key_id() and razorpay_key_secret())


def upi_id() -> str:
    return _env("PHARMACY_UPI_ID", "sanjeevani.pharmacy@upi")


def counter_name() -> str:
    return _env("PHARMACY_COUNTER_NAME", "Sanjeevani Clinic Pharmacy")


def payment_note() -> str:
    return _env("PHARMACY_PAYMENT_NOTE", "Pay at counter for CASH orders")


def image_for_qr() -> str:
    """The QR image the order page shows. Ships with the project."""
    return _env("PHARMACY_QR_IMAGE", "/static/images/dummy_payment_qr.png")


def gateway_config() -> dict:
    """Safe-to-expose settings for the front-end."""

    return {
        "provider": "razorpay" if razorpay_enabled() else "simulated",
        "razorpay_enabled": razorpay_enabled(),
        "key_id": razorpay_key_id() or None,
        "upi_id": upi_id(),
        "counter_name": counter_name(),
        "qr_image": image_for_qr(),
        "cash_note": payment_note(),
        "currency": "INR",
    }


# =========================================================
# AMOUNTS
# =========================================================

def paise(amount) -> int:
    try:
        return int(round(float(amount or 0) * 100))
    except (TypeError, ValueError):
        return 0


def rupees(amount) -> float:
    try:
        return round(float(amount or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def format_inr(amount) -> str:
    value = rupees(amount)
    whole, _, fraction = f"{value:,.2f}".partition(".")
    return f"Rs {whole}.{fraction}"


def upi_string(amount, *, order_no: str | None = None) -> str:
    """`upi://pay?...` - paste into any UPI app, or feed a real QR generator."""

    payee = re.sub(r"[^A-Za-z0-9._-]", "", upi_id())
    note = (order_no or "pharmacy order").replace(" ", "-")

    return (
        f"upi://pay?pa={payee}"
        f"&pn={re.sub(r'[^A-Za-z0-9 ._-]', '', counter_name())}"
        f"&am={rupees(amount):.2f}"
        f"&cu=INR&tn={note}"
    )


# =========================================================
# SIGNATURES
# =========================================================

def expected_signature(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    secret: str | None = None
) -> str:
    secret = secret or razorpay_key_secret()
    message = f"{razorpay_order_id}|{razorpay_payment_id}"
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def verify_razorpay_signature(
    *,
    razorpay_order_id: str | None,
    razorpay_payment_id: str | None,
    razorpay_signature: str | None
) -> tuple[bool, str]:
    """(ok, reason). Never trusts the browser, only the HMAC."""

    if not razorpay_enabled():
        return False, "Razorpay is not configured on this server"

    if not all((razorpay_order_id, razorpay_payment_id, razorpay_signature)):
        return False, "Missing Razorpay order id, payment id or signature"

    if not re.fullmatch(r"[0-9a-f]{64}", razorpay_signature.strip()):
        return False, "Signature is not a sha256 hex string"

    expected = expected_signature(
        razorpay_order_id.strip(),
        razorpay_payment_id.strip()
    )

    if not hmac.compare_digest(expected, razorpay_signature.strip().lower()):
        return False, "Signature mismatch - payment not verified"

    return True, "verified"


def simulated_transaction_id() -> str:
    return f"SJV{uuid4().hex[:10].upper()}"


def payment_provider_label(order) -> str:
    provider = (getattr(order, "payment_provider", "") or "").upper()
    return {
        "RAZORPAY": "Razorpay",
        "SIMULATED": "UPI / QR (simulated)",
        "CASH_COUNTER": "Cash at counter",
    }.get(provider, provider or "-")
