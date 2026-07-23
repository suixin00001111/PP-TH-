"""B-layer handoff helpers after Phase4 authorize.

A-layer success yields return_url / billing agreement evidence.
Merchant follow (pm-redirects / setup_intent / checkout verify) is optional
and intentionally separate — same split as BR pure protocol packages.

This module only normalizes and persists B-layer fields so a later HTTP
merchant completer can replay without browser.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


BA_RE = re.compile(r"BA-[A-Za-z0-9]{8,80}")
SETI_RE = re.compile(r"seti_[A-Za-z0-9]+")
SECRET_RE = re.compile(r"seti_[A-Za-z0-9]+_secret_[A-Za-z0-9]+")
CS_RE = re.compile(r"cs_(?:test|live)_[A-Za-z0-9]+")


def extract_query(url: str) -> dict[str, str]:
    if not url:
        return {}
    q = parse_qs(urlparse(url).query)
    return {k: (v[0] if v else "") for k, v in q.items()}


def build_b_layer_evidence(result: dict[str, Any]) -> dict[str, Any]:
    """Force a complete B-layer evidence object from A-layer result."""
    return_url = (
        result.get("return_url")
        or result.get("returnURL")
        or (result.get("data") or {}).get("return_url")
        or ""
    )
    if isinstance(return_url, dict):
        return_url = return_url.get("href") or return_url.get("url") or ""
    return_url = str(return_url or "").strip()

    final_redirect = (
        result.get("final_redirect_url")
        or result.get("redirect_url")
        or return_url
    )
    q: dict[str, str] = {}
    for candidate_url in (return_url, str(final_redirect or "")):
        for key, value in extract_query(candidate_url).items():
            q.setdefault(key, value)

    setup_intent = (
        result.get("setup_intent")
        or q.get("setup_intent")
        or q.get("setup_intent_id")
        or ""
    )
    secret = (
        result.get("setup_intent_client_secret")
        or q.get("setup_intent_client_secret")
        or q.get("client_secret")
        or ""
    )
    if not setup_intent and secret:
        m = SETI_RE.search(secret)
        if m:
            setup_intent = m.group(0)
    if not secret and return_url:
        m = SECRET_RE.search(unquote(return_url))
        if m:
            secret = m.group(0)
    cs_id = result.get("cs_id") or q.get("cs_id") or ""
    if not cs_id and return_url:
        m = CS_RE.search(unquote(return_url))
        if m:
            cs_id = m.group(0)

    stripe_return_status = (
        result.get("stripe_return_status")
        or result.get("redirect_status")
        or q.get("redirect_status")
        or q.get("status")
        or ""
    )

    ba = result.get("billing_agreement_id") or result.get("ba_token") or ""
    if not ba:
        blob = json.dumps(result, ensure_ascii=False)
        m = BA_RE.search(blob)
        if m:
            ba = m.group(0)

    return {
        "region": "TH",
        "return_url": return_url,
        "final_redirect_url": str(final_redirect or ""),
        "setup_intent": setup_intent,
        "setup_intent_client_secret": secret,
        "stripe_return_status": stripe_return_status,
        "cs_id": cs_id,
        "billing_agreement_id": ba,
        "session_cookies": result.get("session_cookies") or result.get("cookies") or {},
        "protocol_mode": "http_only_full_protocol",
        "source": "thailand_a_layer_phase4",
    }


def persist_b_layer_evidence(job_dir: str | Path, result: dict[str, Any]) -> Path:
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    evidence = build_b_layer_evidence(result)
    path = job_dir / "b_layer_evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    # also write replay input
    replay = {
        "region": "TH",
        "b_layer": evidence,
        "return_url": evidence.get("return_url"),
        "setup_intent_client_secret": evidence.get("setup_intent_client_secret"),
    }
    (job_dir / "merchant_replay_input.json").write_text(
        json.dumps(replay, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path
