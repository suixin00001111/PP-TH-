"""Country protocol maturity matrix.

Gold countries are intentionally small and should be treated as the primary
supported set. Remaining markets are experimental: protocol knobs exist, but
depth of validation is lower.
"""
from __future__ import annotations

from typing import Any

# Primary validated set
GOLD_REGIONS: tuple[str, ...] = ("TH", "JP", "US", "BR", "GB")

# Secondary markets with higher practical demand
SUPPORTED_REGIONS: tuple[str, ...] = (
    "TH", "JP", "US", "BR", "GB",
    "KR", "TW", "HK", "SG", "MY", "ID", "PH", "VN", "CN",
    "AU", "NZ", "CA", "DE", "FR", "ES", "IT", "NL", "MX",
)

# Capability hints (documentation / UI only — not hard gates)
CAPABILITY: dict[str, dict[str, Any]] = {
    "TH": {
        "tier": "gold",
        "phase0": "validated",
        "locale": "validated",
        "address": "deep",
        "phone": "deep",
        "card_bin": "deep",
        "content": "deep",
        "identity": "none",
        "sms_mapping": "mapped",
        "notes": "Gold market; deep phone/address/BIN/content pools",
    },
    "JP": {
        "tier": "gold",
        "phase0": "validated",
        "locale": "validated",
        "address": "deep",
        "phone": "deep",
        "card_bin": "deep",
        "content": "solid",
        "identity": "none",
        "sms_mapping": "mapped",
        "notes": "Gold multi-country target with curated JP pools",
    },
    "US": {
        "tier": "gold",
        "phase0": "validated",
        "locale": "validated",
        "address": "deep",
        "phone": "deep",
        "card_bin": "deep",
        "content": "solid",
        "identity": "none",
        "sms_mapping": "mapped",
        "notes": "Gold multi-country target with curated US pools",
    },
    "BR": {
        "tier": "gold",
        "phase0": "validated",
        "locale": "validated",
        "address": "deep",
        "phone": "deep",
        "card_bin": "deep",
        "content": "solid",
        "identity": "CPF",
        "sms_mapping": "mapped",
        "notes": "Brazil-depth risk/session reference + CPF identity + local BINs",
    },
    "GB": {
        "tier": "gold",
        "phase0": "validated",
        "locale": "validated",
        "address": "deep",
        "phone": "deep",
        "card_bin": "deep",
        "content": "solid",
        "identity": "none",
        "sms_mapping": "mapped",
        "notes": "Gold multi-country target with curated GB pools",
    },
    "KR": {"tier": "supported", "address": "deep", "phone": "deep", "card_bin": "solid", "content": "solid", "identity": "none", "sms_mapping": "mapped", "notes": "Solid curated pools"},
    "VN": {"tier": "supported", "address": "deep", "phone": "deep", "card_bin": "solid", "content": "solid", "identity": "none", "sms_mapping": "mapped", "notes": "Solid curated pools"},
    "CN": {"tier": "supported", "address": "deep", "phone": "deep", "card_bin": "solid", "content": "solid", "identity": "none", "sms_mapping": "mapped", "notes": "Solid curated pools"},
    "HK": {"tier": "supported", "address": "deep", "phone": "deep", "card_bin": "solid", "content": "solid", "identity": "none", "sms_mapping": "mapped", "notes": "Solid curated pools"},
    "NL": {"tier": "supported", "address": "deep", "phone": "deep", "card_bin": "solid", "content": "solid", "identity": "none", "sms_mapping": "mapped", "notes": "Solid curated pools"},
}


def region_tier(code: str | None) -> str:
    c = (code or "").strip().upper()
    if c in GOLD_REGIONS:
        return "gold"
    if c in SUPPORTED_REGIONS:
        return "supported"
    return "experimental"


def region_capability(code: str | None) -> dict[str, Any]:
    c = (code or "").strip().upper()
    base = {
        "code": c or "TH",
        "tier": region_tier(c),
        "phase0": "experimental",
        "locale": "template",
        "address": "template",
        "identity": "none",
        "sms_mapping": "mapped_or_fallback",
        "notes": "Protocol profile exists; treat as experimental",
    }
    if c in CAPABILITY:
        base.update(CAPABILITY[c])
        base["code"] = c
        base["tier"] = region_tier(c)
    return base


def annotate_region_public(item: dict[str, Any]) -> dict[str, Any]:
    code = str(item.get("code") or "")
    cap = region_capability(code)
    out = dict(item)
    out["tier"] = cap["tier"]
    out["maturity"] = {
        "phase0": cap.get("phase0"),
        "locale": cap.get("locale"),
        "address": cap.get("address"),
        "phone": cap.get("phone"),
        "card_bin": cap.get("card_bin"),
        "content": cap.get("content"),
        "identity": cap.get("identity"),
        "sms_mapping": cap.get("sms_mapping"),
        "notes": cap.get("notes"),
    }
    out["recommended"] = cap["tier"] == "gold"
    return out


def list_matrix_public(regions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    items = [annotate_region_public(r) for r in (regions or [])]
    return {
        "gold": list(GOLD_REGIONS),
        "supported": list(SUPPORTED_REGIONS),
        "default": "TH",
        "regions": items,
    }
