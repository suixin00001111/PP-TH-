"""A / B / C layer status normalization for job results.

A-layer: PayPal BA authorize (Phase 0-4)
B-layer: return_url / pm-redirects / setup_intent evidence
C-layer: checkout/verify / chatgpt land / accounts check
"""
from __future__ import annotations

from typing import Any


def _a_status(result: dict[str, Any]) -> str:
    status = str(result.get("status") or "").strip().lower()
    if status in {"success", "ok", "completed", "authorized"}:
        return "success"
    if status in {"awaiting_otp", "waiting_otp", "otp"}:
        return "awaiting_otp"
    if status in {"awaiting_captcha", "captcha"}:
        return "awaiting_captcha"
    if status in {"failed", "error", "fail"}:
        return "failed"
    if status:
        return status
    if result.get("return_url") or result.get("billing_agreement_id"):
        return "success"
    return "unknown"


def _merchant_status(merchant: dict[str, Any] | None) -> str:
    if not merchant:
        return "missing"
    return str(
        merchant.get("merchant_chain_status")
        or merchant.get("status")
        or "unknown"
    ).strip() or "unknown"


def _b_from_merchant(ms: str, result: dict[str, Any], merchant: dict[str, Any] | None) -> str:
    if ms in {"skipped", "skipped_by_config"}:
        return "skipped"
    if ms in {"no_urls"}:
        return "no_urls"
    if result.get("b_layer") or (merchant or {}).get("return_url") or result.get("return_url"):
        if ms in {
            "full_success_b_c",
            "merchant_callback_ok_pending_ui",
            "chatgpt_landed",
            "processing_payment",
            "stuck_processing_payment",
            "callback_failed",
            "incomplete",
        }:
            return "ok" if ms not in {"callback_failed", "no_urls"} else "failed"
        return "ok"
    return "unknown"


def _c_from_merchant(ms: str) -> str:
    if ms in {"skipped", "skipped_by_config"}:
        return "skipped"
    if ms in {"full_success_b_c"}:
        return "success"
    if ms in {"chatgpt_landed", "merchant_callback_ok_pending_ui"}:
        return "partial"
    if ms in {"processing_payment", "stuck_processing_payment"}:
        return "processing"
    if ms in {"callback_failed"}:
        return "failed"
    if ms in {"incomplete", "no_urls", "missing", "unknown"}:
        return ms if ms != "missing" else "unknown"
    return ms or "unknown"


def annotate_layer_status(
    result: dict[str, Any],
    *,
    merchant: dict[str, Any] | None = None,
    continue_merchant: bool = False,
) -> dict[str, Any]:
    """Mutate and return result with a/b/c layer statuses."""
    if not isinstance(result, dict):
        return result

    a_status = _a_status(result)
    result["a_layer_status"] = a_status

    if not continue_merchant:
        result["b_layer_status"] = "skipped"
        result["c_layer_status"] = "skipped"
        result.setdefault("merchant_chain_status", "skipped_by_config")
        result.setdefault("settlement_status", "skipped_by_config")
        result["layers"] = {
            "a": a_status,
            "b": "skipped",
            "c": "skipped",
            "continue_merchant": False,
        }
        return result

    ms = _merchant_status(merchant if merchant is not None else result.get("merchant_chain"))
    if merchant is not None:
        result["merchant_chain"] = merchant
        result["merchant_chain_status"] = ms
        if merchant.get("settlement_status") is not None:
            result["settlement_status"] = merchant.get("settlement_status")

    b_status = _b_from_merchant(ms, result, merchant)
    c_status = _c_from_merchant(ms)
    result["b_layer_status"] = b_status
    result["c_layer_status"] = c_status
    result["layers"] = {
        "a": a_status,
        "b": b_status,
        "c": c_status,
        "continue_merchant": True,
        "merchant_chain_status": ms,
    }
    return result
