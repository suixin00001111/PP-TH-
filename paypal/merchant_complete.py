"""Merchant half-chain after PayPal BA authorize (layers B/C).

Ground-truth package: a local FULL_SUCCESS_A_B_C fixture (not shipped).

Observed chain in 成功.har:
  PayPal authorize
    -> pm-redirects.stripe.com/return/?status=success
    -> pay.openai.com/c/pay/...?redirect_status=pending|succeeded&setup_intent=...
         &setup_intent_client_secret=...&success_return_url=chatgpt.com/checkout/verify
    -> chatgpt.com/checkout/verify (Processing payment intermediate)
    -> chatgpt.com/ land + accounts/check Plus

Full-protocol mode (BR-style pure protocol, NO real browser / remote Chromium):
  After A (billing.authorize) completes, continue B/C entirely via HTTP:
    return_url -> pm-redirects / pay.openai
    -> setup_intent retrieve (terminal status)
    -> force success_return_url / checkout/verify
    -> leave-verify / chatgpt land (HTTP redirect + body signals)
    -> accounts/check Plus (optional ChatGPT cookies)
  Do NOT use browser_action / RemoteBrowser / address-bar navigation for B/C.
  pay.153 browser/frame is only for CAPTCHA observation, not merchant half-chain.
"""

from __future__ import annotations

import re
import time
import os
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import json
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LogFn = Callable[[str], None]

HOP_HOSTS = (
    "pm-redirects.stripe.com",
    "pay.openai.com",
    "checkout.stripe.com",
    "chatgpt.com",
)
LEGACY_BROWSER_KEYS = {
    "browser_continuation",
    "merchant_same_session",
    "browser_hops",
    "browser_client",
    "browser_job_id",
    "browser_driver",
    "force_browser",
}

PROCESSING_TEXT_RE = re.compile(
    r"processing payment|processing your payment|正在处理付款|being processed|please wait",
    re.I,
)
VERIFY_DONE_RE = re.compile(
    r"subscription|plus is active|already active|payment (?:was )?successful|"
    r"billing updated|you.re all set|已开通|订阅成功|plan is active|welcome to plus",
    re.I,
)
VERIFY_FAIL_RE = re.compile(
    r"payment failed|setup.?intent.?fail|unable to|something went wrong|declined|"
    r"redirect_status=failed|not successful|try again",
    re.I,
)


def _log(log: LogFn | None, message: str) -> None:
    if log:
        log(message)


def _scrub(url: str) -> str:
    text = str(url or "")
    text = re.sub(r"cs_live_[A-Za-z0-9]+", "cs_live_REDACTED", text)
    text = re.sub(r"seti_[A-Za-z0-9]+", "seti_REDACTED", text)
    text = re.sub(r"BA-[A-Z0-9]+", "BA-REDACTED", text)
    text = re.sub(r"EC-[A-Z0-9]+", "EC-REDACTED", text)
    text = re.sub(r"sa_nonce_[A-Za-z0-9]+", "sa_nonce_REDACTED", text)
    if len(text) > 180:
        return text[:180] + "..."
    return text


def _qs(url: str) -> dict[str, str]:
    try:
        parsed = urlparse(url)
        return {k: (v[0] if v else "") for k, v in parse_qs(parsed.query).items()}
    except Exception:
        return {}


def extract_urls_from_html(html: str, base: str = "") -> list[str]:
    found: list[str] = []
    patterns = [
        r'href=["\'](https?://[^"\']+)["\']',
        r'content=["\'](https?://[^"\']+)["\']',
        r'url["\']?\s*[:=]\s*["\'](https?://[^"\']+)["\']',
        r'window\.location(?:\.href)?\s*=\s*["\'](https?://[^"\']+)["\']',
        r'location\.replace\(\s*["\'](https?://[^"\']+)["\']',
        r'location\.assign\(\s*["\'](https?://[^"\']+)["\']',
        r'http-equiv=["\']refresh["\'][^>]*content=["\'][^"\']*url=([^"\']+)["\']',
        r'content=["\']\d+\s*;\s*url=([^"\']+)["\']',
        r'(https://(?:pm-redirects\.stripe\.com|pay\.openai\.com|chatgpt\.com/checkout)[^"\'\s<>]+)',
        r'(https%3A%2F%2F(?:pm-redirects\.stripe\.com|pay\.openai\.com|chatgpt\.com%2Fcheckout)[^"\'\s<>]+)',
    ]
    for pat in patterns:
        for m in re.finditer(pat, html or "", re.I):
            url = m.group(1)
            if base and url.startswith("/"):
                url = urljoin(base, url)
            found.append(url)
    for m in re.finditer(r"url=([^\"'>\s]+)", html or "", re.I):
        url = m.group(1).strip("'\"")
        if url.startswith("http") or url.startswith("/") or url.lower().startswith("http%3a"):
            if base and url.startswith("/"):
                url = urljoin(base, url)
            found.append(url)
    # success_return_url may be nested/encoded inside pay.openai query or body JSON
    for m in re.finditer(r"success_return_url=([^&\"'\s<>]+)", html or "", re.I):
        found.append(unquote(m.group(1)))
    out: list[str] = []
    seen: set[str] = set()
    for u in found:
        u = unquote(u).strip().rstrip(").,;'\"\\")
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def pick_next_hop(candidates: list[str], current: str) -> str:
    priority = [
        "chatgpt.com/checkout/verify",
        "pm-redirects.stripe.com",
        "pay.openai.com/c/pay/",
        "pay.openai.com",
        "chatgpt.com/checkout/",
        "chatgpt.com/",
        "checkout.stripe.com",
    ]
    scored: list[tuple[int, str]] = []
    for url in candidates:
        if not url or url == current:
            continue
        host = (urlparse(url).netloc or "").lower()
        if host in {"api.stripe.com", "js.stripe.com", "m.stripe.com"}:
            continue
        if host.endswith("stripe.com") and "pm-redirects" not in host and "checkout.stripe.com" not in host:
            if "checkout.stripe.com" not in url and "pm-redirects" not in url:
                continue
        if not any(h in host or h in url for h in HOP_HOSTS):
            continue
        score = 50
        for i, key in enumerate(priority):
            if key in url:
                score = i
                break
        if "redirect_status=succeeded" in url:
            score -= 5
        if "redirect_status=failed" in url:
            score += 20
        if "checkout/verify" in url:
            score -= 3
        scored.append((score, url))
    scored.sort(key=lambda x: x[0])
    return scored[0][1] if scored else ""


def classify_hop(url: str) -> str:
    u = str(url or "").lower()
    if "pm-redirects.stripe.com" in u:
        return "stripe_return"
    if "pay.openai.com" in u:
        return "openai_pay"
    if "checkout/verify" in u:
        return "checkout_verify"
    if "chatgpt.com" in u:
        return "chatgpt_land"
    if "checkout.stripe.com" in u:
        return "stripe_checkout"
    return "other"


def build_session(user_agent: str | None = None, proxies: list[str] | None = None) -> requests.Session:
    session = requests.Session()
    session.verify = False
    session.headers.update(
        {
            "User-Agent": user_agent
            or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    if proxies:
        raw = str(proxies[0] or "").strip()
        if raw:
            proxy_url = ""
            if raw.startswith("http://") or raw.startswith("https://") or raw.startswith("socks"):
                proxy_url = raw
            else:
                parts = raw.split(":")
                if len(parts) >= 4:
                    host, port, user = parts[0], parts[1], parts[2]
                    password = ":".join(parts[3:])
                    proxy_url = f"http://{user}:{password}@{host}:{port}"
                elif len(parts) == 2:
                    proxy_url = f"http://{parts[0]}:{parts[1]}"
            if proxy_url:
                session.proxies.update({"http": proxy_url, "https": proxy_url})
    return session


def _extract_cs_id(url: str) -> str:
    m = re.search(r"(cs_live_[A-Za-z0-9]+|cs_test_[A-Za-z0-9]+)", url or "")
    return m.group(1) if m else ""


def _extract_pk(html: str) -> str:
    m = re.search(r"(pk_live_[A-Za-z0-9]+|pk_test_[A-Za-z0-9]+)", html or "")
    return m.group(1) if m else ""


def _extract_setup_intent_client_secret(*blobs: str) -> str:
    for blob in blobs:
        m = re.search(r"(seti_[A-Za-z0-9]+_secret_[A-Za-z0-9]+)", blob or "")
        if m:
            return m.group(1)
    return ""


def _extract_setup_intent_id(*blobs: str) -> str:
    for blob in blobs:
        for m in re.finditer(r"(seti_[A-Za-z0-9]{10,})", blob or ""):
            val = m.group(1)
            if "_secret_" not in val:
                return val
    secret = _extract_setup_intent_client_secret(*blobs)
    if secret and "_secret_" in secret:
        return secret.split("_secret_", 1)[0]
    return ""



def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _dig_mapping(obj: Any, *keys: str) -> Any:
    cur = obj
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def normalize_merchant_job_result(job_result: dict[str, Any] | None) -> dict[str, Any]:
    """Flatten pay.153 / nested A-layer payloads into B-layer fields (BR-style).

    Remote completed jobs often nest returnURL under authorize/billing, or only
    expose verification_url. Without normalizing, half-chain starts as a bare
    verify URL and cannot replay full B→C.
    """
    raw = {
        k: v for k, v in dict(job_result or {}).items() if k not in LEGACY_BROWSER_KEYS
    }
    candidates: list[Any] = [raw]
    for key in ("result", "data", "payload", "authorize", "billing", "settlement", "merchant"):
        value = raw.get(key)
        if isinstance(value, dict):
            candidates.append(value)
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            candidates.append(value[0])

    # GraphQL-style: data.billing.authorize.returnURL.href
    authorize = _dig_mapping(raw, "data", "billing", "authorize")
    if isinstance(authorize, dict):
        candidates.append(authorize)
    authorize2 = _dig_mapping(raw, "billing", "authorize")
    if isinstance(authorize2, dict):
        candidates.append(authorize2)

    def pick(*keys: str) -> str:
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            for key in keys:
                if key not in cand:
                    continue
                value = cand.get(key)
                if isinstance(value, dict):
                    href = value.get("href") or value.get("url") or value.get("value")
                    text = _first_nonempty(href, value)
                else:
                    text = _first_nonempty(value)
                if text:
                    return text
        return ""

    return_url = pick("return_url", "returnURL", "returnUrl", "ReturnUrl")
    final_redirect_url = pick(
        "final_redirect_url",
        "final_merchant_url",
        "merchant_url",
        "finalRedirectUrl",
        "redirect_url",
        "redirectUrl",
    )
    verification_url = pick(
        "verification_url",
        "success_return_url",
        "successReturnUrl",
        "checkout_verify_url",
    )
    success_return_url = pick("success_return_url", "successReturnUrl", "verification_url")
    redirect_status = pick("redirect_status", "redirectStatus").lower()
    setup_intent = pick("setup_intent", "setup_intent_id", "setupIntent", "setupIntentId")
    setup_intent_client_secret = pick(
        "setup_intent_client_secret",
        "setupIntentClientSecret",
        "client_secret",
        "clientSecret",
    )
    stripe_return_status = pick("stripe_return_status", "stripeReturnStatus", "pm_return_status").lower()
    settlement_status = pick("settlement_status", "settlementStatus")
    chatgpt_cookie = pick("chatgpt_cookie", "chatgptCookie", "cookie", "cookies")

    # Derive missing fields from known URLs (same idea as Brazil returnURL follow).
    url_pool = [return_url, final_redirect_url, verification_url, success_return_url]
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        for key, value in cand.items():
            if isinstance(value, str) and value.startswith("http"):
                url_pool.append(value)
            elif isinstance(value, dict):
                href = value.get("href") or value.get("url")
                if isinstance(href, str) and href.startswith("http"):
                    url_pool.append(href)

    for url in url_pool:
        if not url:
            continue
        try:
            parsed = urlparse(url)
            qs = {k: (v[0] if v else "") for k, v in parse_qs(parsed.query).items()}
        except Exception:
            continue
        host = (parsed.netloc or "").lower()
        path = parsed.path or ""
        if not return_url and ("pm-redirects.stripe.com" in host or "/return" in path and "stripe" in host):
            return_url = url
        if not final_redirect_url and "pay.openai.com" in host:
            final_redirect_url = url
        if not verification_url and "checkout/verify" in url:
            verification_url = url
        if not success_return_url:
            success_return_url = _first_nonempty(unquote(qs.get("success_return_url") or ""), success_return_url)
            if success_return_url and not verification_url and "checkout/verify" in success_return_url:
                verification_url = success_return_url
        if not redirect_status:
            redirect_status = _first_nonempty(qs.get("redirect_status"), redirect_status).lower()
        if not setup_intent:
            setup_intent = _first_nonempty(qs.get("setup_intent"), setup_intent)
        if not setup_intent_client_secret:
            setup_intent_client_secret = _first_nonempty(
                qs.get("setup_intent_client_secret"),
                setup_intent_client_secret,
            )
        if not stripe_return_status:
            # pm-redirects uses status=success
            if "pm-redirects.stripe.com" in host:
                stripe_return_status = _first_nonempty(qs.get("status"), stripe_return_status).lower()

    if not setup_intent_client_secret:
        setup_intent_client_secret = _extract_setup_intent_client_secret(*[u for u in url_pool if u])
    if not setup_intent:
        setup_intent = _extract_setup_intent_id(*[u for u in url_pool if u], setup_intent_client_secret)
    if not stripe_return_status and return_url and "status=success" in return_url.lower():
        stripe_return_status = "success"

    # Prefer non-empty normalized fields, keep unrelated original keys.
    out = dict(raw)
    out["return_url"] = return_url or _first_nonempty(raw.get("return_url"), raw.get("returnURL"))
    out["final_redirect_url"] = final_redirect_url or _first_nonempty(
        raw.get("final_redirect_url"), raw.get("final_merchant_url")
    )
    out["verification_url"] = verification_url or _first_nonempty(raw.get("verification_url"))
    out["success_return_url"] = success_return_url or _first_nonempty(
        raw.get("success_return_url"), out["verification_url"]
    )
    out["redirect_status"] = redirect_status or _first_nonempty(raw.get("redirect_status")).lower()
    out["setup_intent"] = setup_intent or _first_nonempty(raw.get("setup_intent"))
    out["setup_intent_client_secret"] = setup_intent_client_secret or _first_nonempty(
        raw.get("setup_intent_client_secret")
    )
    out["stripe_return_status"] = stripe_return_status or _first_nonempty(raw.get("stripe_return_status")).lower()
    if settlement_status:
        out["settlement_status"] = settlement_status
    if chatgpt_cookie and not out.get("chatgpt_cookie"):
        out["chatgpt_cookie"] = chatgpt_cookie
    out["protocol_mode"] = "http_only_full_protocol"
    out["b_layer_fields"] = {
        "return_url": out.get("return_url") or "",
        "final_redirect_url": out.get("final_redirect_url") or "",
        "setup_intent": out.get("setup_intent") or "",
        "setup_intent_client_secret": out.get("setup_intent_client_secret") or "",
        "stripe_return_status": out.get("stripe_return_status") or "",
        "success_return_url": out.get("success_return_url") or "",
        "verification_url": out.get("verification_url") or "",
        "redirect_status": out.get("redirect_status") or "",
    }
    return out


def apply_cookie_header(session: requests.Session, cookie_header: str, domain: str = "chatgpt.com") -> int:
    raw = str(cookie_header or "").strip()
    if not raw:
        return 0
    count = 0
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name, value = name.strip(), value.strip()
        if not name:
            continue
        session.cookies.set(name, value, domain=domain, path="/")
        count += 1
    return count


def persist_merchant_session(session: requests.Session, path: str | Path | None) -> str:
    if not path:
        return ""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cookies": [
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path,
                "secure": bool(getattr(c, "secure", False)),
            }
            for c in session.cookies
        ]
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out)


def load_merchant_session(session: requests.Session, path: str | Path | None) -> int:
    if not path:
        return 0
    p = Path(path)
    if not p.exists():
        return 0
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return 0
    count = 0
    for item in payload.get("cookies") or []:
        name = str(item.get("name") or "")
        value = str(item.get("value") or "")
        if not name:
            continue
        session.cookies.set(
            name,
            value,
            domain=item.get("domain") or None,
            path=item.get("path") or "/",
            secure=bool(item.get("secure", False)),
        )
        count += 1
    return count


def _snapshot_session_cookies(session: Any) -> list[dict[str, Any]]:
    jar = getattr(session, "cookies", None)
    if jar is None:
        return []
    cookies: list[dict[str, Any]] = []
    try:
        for c in jar:
            cookies.append(
                {
                    "name": getattr(c, "name", ""),
                    "value": getattr(c, "value", ""),
                    "domain": getattr(c, "domain", ""),
                    "path": getattr(c, "path", "/"),
                    "secure": bool(getattr(c, "secure", False)),
                }
            )
    except Exception:
        return []
    return cookies


def _resolve_merchant_evidence_dir(
    result: dict[str, Any] | None,
    session_path: str | Path | None,
) -> Path | None:
    source = dict(result or {})
    explicit = str(
        source.get("merchant_evidence_dir")
        or source.get("evidence_dir")
        or source.get("job_dir")
        or ""
    ).strip()
    if explicit:
        return Path(explicit)
    if session_path:
        return Path(session_path).parent
    remote_job_id = str(
        source.get("remote_job_id")
        or source.get("job_id")
        or source.get("jobId")
        or ""
    ).strip()
    if not remote_job_id:
        return None
    try:
        from config import RUNTIME_DIR

        return Path(RUNTIME_DIR) / "jobs" / remote_job_id
    except Exception:
        return Path.cwd() / "runtime" / "jobs" / remote_job_id


def _build_merchant_replay_input(source: dict[str, Any]) -> dict[str, Any]:
    """Minimal B→C replay payload — enough to re-run complete_merchant_chain without bare verify."""
    return_url = str(source.get("return_url") or source.get("returnURL") or "")
    final_redirect_url = str(source.get("final_redirect_url") or source.get("final_merchant_url") or "")
    verification_url = str(source.get("verification_url") or "")
    success_return_url = str(source.get("success_return_url") or verification_url or "")
    setup_intent = str(source.get("setup_intent") or "")
    setup_secret = str(source.get("setup_intent_client_secret") or "")
    stripe_return_status = str(source.get("stripe_return_status") or "")
    redirect_status = str(source.get("redirect_status") or "")
    session_path = str(source.get("session_path") or "")
    return {
        "return_url": return_url,
        "final_redirect_url": final_redirect_url,
        "verification_url": verification_url,
        "success_return_url": success_return_url,
        "redirect_status": redirect_status,
        "setup_intent": setup_intent,
        "setup_intent_client_secret": setup_secret,
        "stripe_return_status": stripe_return_status,
        "session_path": session_path,
        "protocol_mode": str(source.get("protocol_mode") or "http_only_full_protocol"),
        "remote_job_id": str(source.get("remote_job_id") or ""),
        # Explicit B-layer evidence block (forced for every dump / replay).
        "b_layer": {
            "return_url": return_url,
            "final_redirect_url": final_redirect_url,
            "setup_intent": setup_intent,
            "setup_intent_client_secret": setup_secret,
            "stripe_return_status": stripe_return_status,
            "session_path": session_path,
        },
    }


def _build_merchant_evidence_payload(
    source: dict[str, Any],
    *,
    phase: str,
    session: Any,
    session_path: str | Path | None,
) -> dict[str, Any]:
    cookies = _snapshot_session_cookies(session)
    return_url = str(source.get("return_url") or source.get("returnURL") or "")
    final_redirect_url = str(source.get("final_redirect_url") or source.get("final_merchant_url") or "")
    setup_intent = str(source.get("setup_intent") or "")
    setup_secret = str(source.get("setup_intent_client_secret") or "")
    stripe_return_status = str(source.get("stripe_return_status") or "")
    session_path_value = str(source.get("session_path") or session_path or "")
    payload: dict[str, Any] = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase": phase,
        "protocol_mode": str(source.get("protocol_mode") or "http_only_full_protocol"),
        "remote_job_id": str(source.get("remote_job_id") or ""),
        "return_url": return_url,
        "final_redirect_url": final_redirect_url,
        "verification_url": str(source.get("verification_url") or ""),
        "success_return_url": str(source.get("success_return_url") or source.get("verification_url") or ""),
        "redirect_status": str(source.get("redirect_status") or ""),
        "setup_intent": setup_intent,
        "setup_intent_client_secret": setup_secret,
        "setup_intent_status": str(source.get("setup_intent_status") or ""),
        "stripe_return_status": stripe_return_status,
        "merchant_chain_status": str(source.get("merchant_chain_status") or ""),
        "settlement_status": str(source.get("settlement_status") or ""),
        "session_path": session_path_value,
        "session_cookie_count": len(cookies),
        "session_cookies": cookies,
        # Forced complete B-layer evidence (never omit keys — empty string if unknown).
        "b_layer": {
            "return_url": return_url,
            "final_redirect_url": final_redirect_url,
            "setup_intent": setup_intent,
            "setup_intent_client_secret": setup_secret,
            "stripe_return_status": stripe_return_status,
            "session_cookies": cookies,
            "session_path": session_path_value,
        },
        "hops": source.get("hops") or [],
        "pay_poll": source.get("pay_poll"),
        "stripe_poll": source.get("stripe_poll"),
        "setup_intent_poll": source.get("setup_intent_poll"),
        "verify": source.get("verify"),
        "account_confirm": source.get("account_confirm"),
        "plus_confirmed": bool(source.get("plus_confirmed")),
        "notes": list(source.get("notes") or []),
    }
    replay_source = {
        **source,
        "session_path": payload["session_path"],
        "protocol_mode": payload["protocol_mode"],
    }
    payload["replay_input"] = _build_merchant_replay_input(replay_source)
    merged_result = source.get("merged_result")
    if isinstance(merged_result, dict):
        payload["merged_result"] = merged_result
    return payload


def persist_merchant_evidence(
    source: dict[str, Any] | None,
    *,
    phase: str,
    session: Any,
    session_path: str | Path | None,
) -> dict[str, str]:
    evidence_dir = _resolve_merchant_evidence_dir(source, session_path)
    if evidence_dir is None:
        return {}
    evidence_dir.mkdir(parents=True, exist_ok=True)
    payload = _build_merchant_evidence_payload(
        dict(source or {}),
        phase=phase,
        session=session,
        session_path=session_path,
    )
    evidence_path = evidence_dir / f"merchant_evidence_{phase}.json"
    latest_path = evidence_dir / "merchant_evidence_latest.json"
    replay_path = evidence_dir / "merchant_replay_input.json"
    evidence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    replay_path.write_text(
        json.dumps(payload.get("replay_input") or {}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "evidence_path": str(evidence_path),
        "latest_path": str(latest_path),
        "replay_input_path": str(replay_path),
        "evidence_dir": str(evidence_dir),
    }


def poll_setup_intent(
    session: requests.Session,
    setup_intent: str = "",
    client_secret: str = "",
    pk: str = "",
    *,
    attempts: int = 12,
    interval: float = 1.5,
    timeout: float = 20.0,
    log: LogFn | None = None,
) -> dict[str, Any]:
    """Retrieve Stripe SetupIntent status (成功.har B proof)."""
    seti = str(setup_intent or "").strip() or _extract_setup_intent_id(client_secret)
    secret = str(client_secret or "").strip()
    if not seti or not secret:
        return {"ok": False, "reason": "missing setup_intent or client_secret", "status": ""}
    if not pk:
        pk = os.getenv("STRIPE_PUBLISHABLE_KEY", "").strip()
    if not pk:
        return {"ok": False, "reason": "missing Stripe publishable key", "setup_intent": seti, "status": ""}
    last: dict[str, Any] = {"ok": False, "setup_intent": seti, "status": ""}
    url = f"https://api.stripe.com/v1/setup_intents/{seti}"
    for i in range(max(1, attempts)):
        _log(log, f"[merchant-seti] poll {i+1}/{attempts}: {seti[:18]}...")
        try:
            resp = session.get(
                url,
                params={"client_secret": secret, "key": pk},
                headers={
                    "Accept": "application/json",
                    "Origin": "https://pay.openai.com",
                    "Referer": "https://pay.openai.com/",
                },
                timeout=timeout,
            )
            body = resp.text or ""
        except Exception as exc:
            last = {"ok": False, "error": str(exc), "attempt": i + 1, "setup_intent": seti}
            time.sleep(interval)
            continue
        status = ""
        last_setup_error = None
        payment_method = ""
        try:
            data = resp.json()
        except Exception:
            data = {}
        if isinstance(data, dict):
            status = str(data.get("status") or "").lower()
            last_setup_error = data.get("last_setup_error")
            payment_method = data.get("payment_method") or ""
        if not status:
            m = re.search(r'"status"\s*:\s*"([a-zA-Z_]+)"', body)
            status = (m.group(1).lower() if m else "")
        last = {
            "ok": status in {"succeeded", "success"},
            "status_code": resp.status_code,
            "status": status,
            "setup_intent": seti,
            "payment_method": payment_method,
            "last_setup_error": last_setup_error,
            "attempt": i + 1,
            "body_snippet": body[:500],
            "failed": status in {"canceled", "cancelled", "requires_payment_method"}
            or bool(last_setup_error)
            or (resp.status_code >= 400 and status not in {"processing", "requires_action", ""}),
        }
        _log(log, f"[merchant-seti] status={status or '-'} http={resp.status_code}")
        if status in {"succeeded", "success", "canceled", "cancelled", "requires_payment_method"} or last_setup_error:
            break
        time.sleep(interval)
    return last


def confirm_account_plus(
    session: requests.Session,
    *,
    timeout: float = 20.0,
    log: LogFn | None = None,
) -> dict[str, Any]:
    """Account-side Plus confirmation after leaving checkout/verify."""
    urls = [
        "https://chatgpt.com/backend-api/accounts/check/v4-2023-04-27?timezone_offset_min=0",
        "https://chatgpt.com/backend-api/accounts/optimized/check",
        "https://chatgpt.com/backend-api/me",
    ]
    last: dict[str, Any] = {"ok": False, "plus": False, "plan": "", "url": ""}
    for url in urls:
        _log(log, f"[merchant-account] GET {_scrub(url)}")
        try:
            resp = session.get(
                url,
                headers={
                    "Accept": "application/json",
                    "Referer": "https://chatgpt.com/",
                    "Origin": "https://chatgpt.com",
                },
                timeout=timeout,
            )
            body = resp.text or ""
        except Exception as exc:
            last = {"ok": False, "error": str(exc), "url": url}
            continue
        plan = ""
        plus = False
        try:
            data = resp.json()
        except Exception:
            data = None
        blob = body.lower()
        if isinstance(data, dict):
            dumped = json.dumps(data, ensure_ascii=False).lower()
            if any(k in dumped for k in ("chatgptplusplan", "chatgpt_plus", 'plan_type": "plus', "is_paid_subscription\": true")):
                plus = True
            m = re.search(r'"plan_type"\s*:\s*"([^"]+)"', dumped)
            if m:
                plan = m.group(1)
            m2 = re.search(r'"subscription_plan"\s*:\s*"([^"]+)"', dumped)
            if m2:
                plan = plan or m2.group(1)
            if plan and "plus" in plan:
                plus = True
        if not plus and any(k in blob for k in ("chatgptplusplan", "plus is active")):
            plus = True
        last = {
            "ok": resp.status_code < 400,
            "status_code": resp.status_code,
            "plus": plus,
            "plan": plan,
            "url": url,
            "body_snippet": body[:500],
        }
        if plus:
            _log(log, f"[merchant-account] Plus confirmed plan={plan or 'plus'}")
            break
        _log(log, f"[merchant-account] http={resp.status_code} plus={plus} plan={plan or '-'}")
    return last



def follow_redirect_chain(
    session: requests.Session,
    start_url: str,
    *,
    max_hops: int = 12,
    timeout: float = 25.0,
    log: LogFn | None = None,
) -> dict[str, Any]:
    current = str(start_url or "").strip()
    hops: list[dict[str, Any]] = []
    seen: set[str] = set()
    final_url = current
    last_status = 0
    last_body = ""

    for i in range(max_hops):
        if not current or current in seen:
            break
        seen.add(current)
        hop_kind = classify_hop(current)
        _log(log, f"[merchant-hop {i+1}] {hop_kind}: {_scrub(current)}")
        try:
            resp = session.get(current, timeout=timeout, allow_redirects=False)
        except Exception as exc:
            hops.append({"url": current, "error": str(exc), "kind": hop_kind})
            _log(log, f"[merchant-hop] request failed: {exc}")
            break

        last_status = int(resp.status_code)
        final_url = str(resp.url or current)
        location = resp.headers.get("Location") or resp.headers.get("location") or ""
        try:
            body = resp.text or ""
        except Exception:
            body = ""
        last_body = body
        hops.append(
            {
                "url": current,
                "status": last_status,
                "kind": hop_kind,
                "location": location[:300] if location else "",
            }
        )

        next_url = ""
        if last_status in {301, 302, 303, 307, 308} and location:
            next_url = urljoin(current, location)
        else:
            candidates = extract_urls_from_html(body, base=current)
            next_url = pick_next_hop(candidates, current)
        if not next_url or next_url == current:
            break
        current = next_url
        final_url = next_url

    qs = _qs(final_url)
    redirect_status = (qs.get("redirect_status") or "").lower()
    setup_intent = qs.get("setup_intent") or ""
    setup_intent_client_secret = qs.get("setup_intent_client_secret") or ""
    stripe_return_status = ""
    chatgpt_land_url = ""
    verification_url = ""
    success_return_url = ""
    hop_blob = "\n".join([str(h.get("url") or "") for h in hops] + [last_body[:12000], final_url, start_url])

    if "checkout/verify" in final_url:
        verification_url = final_url
    success_return = qs.get("success_return_url") or ""
    if success_return:
        success_return_url = unquote(success_return)
        if not verification_url:
            verification_url = success_return_url

    if not verification_url:
        m = re.search(r"https://chatgpt\.com/checkout/verify[^\s\"'<>]+", hop_blob, re.I)
        if m:
            verification_url = m.group(0).rstrip(").,;'\"")
        else:
            m = re.search(r"success_return_url=([^&\"'\s<>]+)", hop_blob, re.I)
            if m:
                verification_url = unquote(m.group(1)).rstrip(").,;'\"")
                success_return_url = success_return_url or verification_url

    if not setup_intent_client_secret:
        setup_intent_client_secret = _extract_setup_intent_client_secret(hop_blob)
    if not setup_intent:
        setup_intent = _extract_setup_intent_id(hop_blob, setup_intent_client_secret)

    for h in hops:
        hu = str(h.get("url") or "")
        hqs = _qs(hu)
        if "pm-redirects.stripe.com" in hu:
            stripe_return_status = (hqs.get("status") or stripe_return_status or "").lower()
        if hqs.get("redirect_status"):
            redirect_status = hqs.get("redirect_status", "").lower() or redirect_status
        if hqs.get("setup_intent"):
            setup_intent = hqs.get("setup_intent") or setup_intent
        if hqs.get("setup_intent_client_secret"):
            setup_intent_client_secret = hqs.get("setup_intent_client_secret") or setup_intent_client_secret
        if hqs.get("success_return_url"):
            success_return_url = unquote(hqs.get("success_return_url") or "") or success_return_url
            if not verification_url:
                verification_url = success_return_url
        if "chatgpt.com" in hu and "checkout/verify" not in hu and "/cdn" not in hu and "backend-api" not in hu:
            chatgpt_land_url = hu

    if "chatgpt.com" in final_url and "checkout/verify" not in final_url and "/cdn" not in final_url:
        chatgpt_land_url = final_url or chatgpt_land_url

    cs_id = (
        _extract_cs_id(final_url)
        or _extract_cs_id(start_url)
        or _extract_cs_id(hop_blob)
        or _extract_cs_id(success_return_url)
        or _extract_cs_id(verification_url)
    )

    return {
        "start_url": start_url,
        "final_url": final_url,
        "final_status": last_status,
        "redirect_status": redirect_status,
        "setup_intent": setup_intent,
        "setup_intent_client_secret": setup_intent_client_secret,
        "stripe_return_status": stripe_return_status,
        "verification_url": verification_url,
        "success_return_url": success_return_url or verification_url,
        "chatgpt_land_url": chatgpt_land_url,
        "hops": hops,
        "body_snippet": (last_body or "")[:2000],
        "pk": _extract_pk(hop_blob),
        "cs_id": cs_id,
    }


def poll_openai_pay_status(
    session: requests.Session,
    pay_url: str,
    *,
    attempts: int = 10,
    interval: float = 2.0,
    timeout: float = 25.0,
    log: LogFn | None = None,
) -> dict[str, Any]:
    """Poll pay.openai.com URL while redirect_status=pending (成功.har intermediate)."""
    url = str(pay_url or "").strip()
    if not url or "pay.openai.com" not in url:
        return {"ok": False, "reason": "not pay.openai url"}

    last: dict[str, Any] = {"ok": False, "url": url}
    for i in range(max(1, attempts)):
        _log(log, f"[merchant-pay] poll {i+1}/{attempts}: {_scrub(url)}")
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
        except Exception as exc:
            last = {"ok": False, "error": str(exc), "url": url, "attempt": i + 1}
            time.sleep(interval)
            continue
        final = str(resp.url or url)
        try:
            body = resp.text or ""
        except Exception:
            body = ""
        qs = _qs(final)
        # also scan body for redirect_status transitions
        m = re.search(r"redirect_status=([a-zA-Z_]+)", body)
        body_rs = (m.group(1).lower() if m else "")
        redirect_status = (qs.get("redirect_status") or body_rs or "").lower()
        setup_intent = qs.get("setup_intent") or ""
        success_return = unquote(qs.get("success_return_url") or "")
        if not success_return:
            m2 = re.search(r"https://chatgpt\.com/checkout/verify[^\s\"'<>]+", body, re.I)
            if m2:
                success_return = m2.group(0).rstrip(").,;'\"")
        if not setup_intent:
            setup_intent = _extract_setup_intent_id(final, body)
        setup_secret = qs.get("setup_intent_client_secret") or _extract_setup_intent_client_secret(final, body)
        last = {
            "ok": redirect_status in {"succeeded", "success"} or bool(success_return),
            "status_code": resp.status_code,
            "url": final,
            "redirect_status": redirect_status,
            "setup_intent": setup_intent,
            "setup_intent_client_secret": setup_secret,
            "success_return_url": success_return,
            "pk": _extract_pk(body),
            "cs_id": _extract_cs_id(final) or _extract_cs_id(body),
            "attempt": i + 1,
            "body_snippet": body[:600],
        }
        _log(
            log,
            f"[merchant-pay] redirect_status={redirect_status or '-'} "
            f"setup_intent={'yes' if setup_intent else 'no'} "
            f"success_return={'yes' if success_return else 'no'}",
        )
        if redirect_status in {"succeeded", "success", "failed"}:
            break
        # keep polling while pending
        time.sleep(interval)
    return last


def poll_payment_pages(
    session: requests.Session,
    cs_id: str,
    pk: str = "",
    *,
    attempts: int = 8,
    interval: float = 1.5,
    timeout: float = 20.0,
    log: LogFn | None = None,
) -> dict[str, Any]:
    """Poll Stripe payment_pages like 成功.har (GET + /init)."""
    cs_id = str(cs_id or "").strip()
    if not cs_id:
        return {"ok": False, "reason": "no cs_id"}
    last: dict[str, Any] = {"ok": False, "cs_id": cs_id}
    # 成功.har hits payment_pages/{cs}/init; also try base path as fallback.
    endpoints = [
        f"https://api.stripe.com/v1/payment_pages/{cs_id}/init",
        f"https://api.stripe.com/v1/payment_pages/{cs_id}",
    ]
    for i in range(max(1, attempts)):
        _log(log, f"[merchant-stripe] payment_pages poll {i+1}/{attempts} cs={cs_id[:16]}...")
        params: dict[str, str] = {}
        if pk:
            params["key"] = pk
        body = ""
        status_code = 0
        try:
            for ep in endpoints:
                resp = session.get(
                    ep,
                    params=params or None,
                    headers={
                        "Accept": "application/json",
                        "Origin": "https://pay.openai.com",
                        "Referer": "https://pay.openai.com/",
                    },
                    timeout=timeout,
                )
                status_code = int(resp.status_code)
                body = resp.text or ""
                if status_code < 500 and body:
                    break
        except Exception as exc:
            last = {"ok": False, "error": str(exc), "attempt": i + 1}
            time.sleep(interval)
            continue
        redirect = ""
        m = re.search(r"redirect_status['\"]?\s*[:=]\s*['\"]([a-zA-Z_]+)", body)
        if m:
            redirect = m.group(1).lower()
        m2 = re.search(r"https://chatgpt\.com/checkout/verify[^\s\"'<>]+", body)
        verify = m2.group(0).rstrip(").,;'\"") if m2 else ""
        if not verify:
            m2b = re.search(r"success_return_url['\"]?\s*[:=]\s*['\"]([^'\"]+)", body)
            if m2b:
                verify = unquote(m2b.group(1)).rstrip(").,;'\"")
        seti = _extract_setup_intent_id(body)
        seti_secret = _extract_setup_intent_client_secret(body)
        last = {
            "ok": status_code == 200,
            "status_code": status_code,
            "redirect_status": redirect,
            "verification_url": verify,
            "setup_intent": seti,
            "setup_intent_client_secret": seti_secret,
            "pk": _extract_pk(body) or pk,
            "attempt": i + 1,
            "body_snippet": body[:500],
        }
        if redirect in {"succeeded", "success", "failed"} or verify or seti_secret:
            break
        time.sleep(interval)
    return last


def poll_checkout_verify(
    session: requests.Session,
    verification_url: str,
    *,
    attempts: int = 16,
    interval: float = 2.5,
    timeout: float = 25.0,
    log: LogFn | None = None,
    known_failed: bool = False,
) -> dict[str, Any]:
    """Poll chatgpt checkout/verify — the 'Processing payment' page from the screenshot.

    When known_failed=True (redirect_status=failed already known), do a short confirm
    poll only — do NOT sit on Processing payment for tens of seconds.
    """
    url = str(verification_url or "").strip()
    if not url:
        return {"ok": False, "reason": "no verification_url"}

    # Hard cap: failed callback must not burn full verify budget.
    if known_failed:
        attempts = min(max(1, attempts), 2)
        interval = min(interval, 1.0)

    last: dict[str, Any] = {"ok": False, "url": url}
    processing_seen = False
    auth_block_streak = 0
    for i in range(max(1, attempts)):
        _log(log, f"[merchant-verify] poll {i+1}/{attempts}: {_scrub(url)}")
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
        except Exception as exc:
            last = {"ok": False, "error": str(exc), "url": url, "attempt": i + 1, "state": "error"}
            time.sleep(interval)
            continue

        final = str(resp.url or url)
        try:
            body = resp.text or ""
        except Exception:
            body = ""
        qs = _qs(final)
        text_blob = f"{final}\n{body[:12000]}"
        state = "unknown"

        if PROCESSING_TEXT_RE.search(text_blob) or "checkout/verify" in final:
            processing_seen = True

        if resp.status_code >= 400 and "checkout/verify" in final:
            # unauthenticated console poll often gets 401/403; still means verify URL was hit
            state = "processing" if resp.status_code in {401, 403, 429} else "failed"
            if resp.status_code in {401, 403}:
                auth_block_streak += 1
        elif VERIFY_FAIL_RE.search(text_blob) or qs.get("redirect_status", "").lower() == "failed":
            state = "failed"
            auth_block_streak = 0
        elif "chatgpt.com" in final and "checkout/verify" not in final and resp.status_code < 400:
            # left verify page → 成功.har C landing style
            state = "landed"
            auth_block_streak = 0
        elif VERIFY_DONE_RE.search(text_blob) and resp.status_code < 400:
            state = "likely_done"
            auth_block_streak = 0
        elif PROCESSING_TEXT_RE.search(text_blob) or "checkout/verify" in final:
            state = "processing"
        else:
            state = "unknown"

        last = {
            "ok": state in {"landed", "likely_done"},
            "state": state,
            "status_code": resp.status_code,
            "url": final,
            "redirect_status": (qs.get("redirect_status") or "").lower(),
            "setup_intent": qs.get("setup_intent") or "",
            "attempt": i + 1,
            "processing_seen": processing_seen,
            "body_snippet": body[:800],
        }
        _log(log, f"[merchant-verify] state={state} http={resp.status_code} processing_seen={processing_seen}")
        if state in {"landed", "likely_done", "failed"}:
            break
        # Early exit: known B-fail or repeated 403 means Processing payment will not clear here.
        if known_failed and processing_seen:
            last["stuck_processing"] = True
            last["early_exit"] = "known_failed"
            last["ok"] = False
            _log(log, "[merchant-verify] early exit: known redirect_status=failed — stop Processing payment poll")
            break
        if auth_block_streak >= 2 and processing_seen:
            last["stuck_processing"] = True
            last["early_exit"] = "auth_blocked"
            last["ok"] = False
            _log(log, "[merchant-verify] early exit: repeated 401/403 on checkout/verify — will not leave Processing payment without session")
            break
        time.sleep(interval)

    # If still processing after all polls, mark stuck_processing
    if last.get("state") == "processing":
        last["stuck_processing"] = True
        last["ok"] = False
    return last


def complete_merchant_chain(
    job_result: dict[str, Any] | None,
    *,
    proxies: list[str] | None = None,
    log: LogFn | None = None,
    follow_hops: int = 12,
    verify_attempts: int = 16,
    verify_interval: float = 2.5,
    pay_poll_attempts: int = 10,
    chatgpt_cookie: str = "",
    session_path: str | None = None,
) -> dict[str, Any]:
    """Run post-authorize merchant B/C as pure HTTP protocol (成功.har path).

    Full protocol (no real browser / no remote Chromium browser_action):
      1) HTTP follow return_url -> pay.openai / pm-redirects
      2) Confirm SetupIntent terminal status via client_secret
      3) Force open success_return_url / checkout/verify over HTTP
      4) Detect leave-verify / chatgpt land from redirects + body
      5) Optional accounts/check Plus with ChatGPT cookies
      6) Persist merchant session cookies for re-runs
    """
    result = normalize_merchant_job_result(job_result)
    return_url = str(result.get("return_url") or result.get("returnURL") or "").strip()
    final_redirect_url = str(result.get("final_redirect_url") or result.get("final_merchant_url") or "").strip()
    verification_url = str(result.get("verification_url") or "").strip()
    existing_redirect = str(result.get("redirect_status") or "").strip().lower()
    known_failed = existing_redirect == "failed" or "redirect_status=failed" in (final_redirect_url or "").lower()
    if known_failed:
        # Do not burn time on pay poll / long verify when B already failed.
        pay_poll_attempts = 0
        verify_attempts = min(int(verify_attempts or 16), 2)
        verify_interval = min(float(verify_interval or 2.5), 1.0)
        follow_hops = min(int(follow_hops or 12), 4)

    out: dict[str, Any] = {
        "attempted": False,
        "verify_exit_detected": False,
        "setup_intent_status": "",
        "setup_intent_poll": None,
        "account_confirm": None,
        "session_path": session_path or "",
        "plus_confirmed": False,
        "return_url": return_url,
        "final_redirect_url": final_redirect_url,
        "verification_url": verification_url,
        "success_return_url": str(result.get("success_return_url") or verification_url or ""),
        "redirect_status": existing_redirect,
        "setup_intent": str(result.get("setup_intent") or ""),
        "setup_intent_client_secret": str(result.get("setup_intent_client_secret") or ""),
        "stripe_return_status": str(result.get("stripe_return_status") or ""),
        "merchant_chain_status": "skipped",
        "settlement_status": str(result.get("settlement_status") or ""),
        "processing_payment_seen": False,
        "stuck_on_processing_payment": False,
        "hops": [],
        "pay_poll": None,
        "stripe_poll": None,
        "verify": None,
        "notes": [],
        "merchant_evidence_pre_path": "",
        "merchant_evidence_post_path": "",
        "merchant_evidence_latest_path": "",
        "merchant_replay_input_path": "",
        "protocol_mode": "http_only_full_protocol",
        "b_layer": {
            "return_url": return_url,
            "final_redirect_url": final_redirect_url,
            "setup_intent": str(result.get("setup_intent") or ""),
            "setup_intent_client_secret": str(result.get("setup_intent_client_secret") or ""),
            "stripe_return_status": str(result.get("stripe_return_status") or ""),
            "session_path": session_path or "",
        },
    }
    if return_url:
        out["notes"].append(f"B-layer return_url present: {_scrub(return_url)}")
    else:
        out["notes"].append(
            "B-layer return_url missing after normalize — half-chain may start from final/verify only"
        )
    if out.get("setup_intent_client_secret"):
        out["notes"].append("B-layer setup_intent_client_secret present (can confirm seti terminal)")
    if out.get("stripe_return_status"):
        out["notes"].append(f"B-layer stripe_return_status={out.get('stripe_return_status')}")

    start = return_url or final_redirect_url or verification_url
    if not start:
        out["notes"].append("no return_url / final_redirect_url / verification_url — cannot run merchant half-chain")
        out["merchant_chain_status"] = "no_urls"
        return out

    out["attempted"] = True
    session = build_session(proxies=proxies)
    loaded = load_merchant_session(session, session_path)
    if loaded:
        out["notes"].append(f"loaded merchant session cookies={loaded} from {session_path}")
        _log(log, f"[merchant] loaded session cookies={loaded}")
    cookie_count = apply_cookie_header(session, chatgpt_cookie or str(result.get("chatgpt_cookie") or ""))
    if cookie_count:
        out["notes"].append(f"applied chatgpt cookies={cookie_count}")
        _log(log, f"[merchant] applied chatgpt cookies={cookie_count}")
    pre_paths = persist_merchant_evidence(
        {**result, **out},
        phase="pre",
        session=session,
        session_path=session_path,
    )
    if pre_paths:
        out["merchant_evidence_pre_path"] = pre_paths.get("evidence_path", "")
        out["merchant_evidence_latest_path"] = pre_paths.get("latest_path", "")
        out["merchant_replay_input_path"] = pre_paths.get("replay_input_path", "")
        out["notes"].append(f"persisted merchant evidence (pre) -> {out['merchant_evidence_pre_path']}")
        _log(log, f"[merchant] evidence pre: {out['merchant_evidence_pre_path']}")
    out["protocol_mode"] = "http_only_full_protocol"

    # ---- Step 1: follow Stripe return / openai pay (HTTP) ----
    # When B already failed, start from final_redirect_url (keeps redirect_status=failed)
    # instead of re-entering return_url which may only show pending and waste time.
    if known_failed and final_redirect_url:
        chain_start = final_redirect_url
    else:
        chain_start = return_url or final_redirect_url
    chain: dict[str, Any] = {}
    if chain_start:
        _log(log, f"[merchant] start half-chain from {_scrub(chain_start)}")
        chain = follow_redirect_chain(session, chain_start, max_hops=follow_hops, log=log)
        out["hops"] = chain.get("hops") or []
        if chain.get("final_url"):
            out["final_redirect_url"] = chain["final_url"]
            final_redirect_url = chain["final_url"]
        if chain.get("redirect_status"):
            out["redirect_status"] = chain["redirect_status"]
        if chain.get("setup_intent"):
            out["setup_intent"] = chain["setup_intent"]
        if chain.get("setup_intent_client_secret"):
            out["setup_intent_client_secret"] = chain["setup_intent_client_secret"]
        if chain.get("stripe_return_status"):
            out["stripe_return_status"] = chain["stripe_return_status"]
        if chain.get("verification_url"):
            out["verification_url"] = chain["verification_url"]
            verification_url = chain["verification_url"]
        if chain.get("success_return_url"):
            out["success_return_url"] = chain["success_return_url"]
        if chain.get("chatgpt_land_url"):
            out["chatgpt_land_url"] = chain["chatgpt_land_url"]
        if chain.get("cs_id"):
            out["cs_id"] = chain["cs_id"]
        if chain.get("pk"):
            out["pk"] = chain["pk"]
        out["notes"].append(
            f"followed merchant chain hops={len(out['hops'])} "
            f"redirect_status={out.get('redirect_status') or '-'} "
            f"final={_scrub(out.get('final_redirect_url') or '')}"
        )
        # If live hop reveals failed, flip known_failed and shrink remaining budget.
        if str(out.get("redirect_status") or "").lower() == "failed":
            known_failed = True
            pay_poll_attempts = 0
            verify_attempts = min(int(verify_attempts or 16), 2)
            out["notes"].append("live hop redirect_status=failed — switch to fast terminal path (no long Processing payment wait)")
    else:
        out["notes"].append("no return/final URL; only verification_url available")

    # ---- Step 1b: intentionally no remote browser hop (pure protocol) ----
    out["notes"].append("merchant B/C protocol mode=http_only_full_protocol (HTTP follow/confirm only; no UI continuation)")

    secret_blob = "\n".join(
        [
            str(return_url or ""),
            str(final_redirect_url or ""),
            str(out.get("final_redirect_url") or ""),
            str(result.get("final_redirect_url") or ""),
            str(result.get("setup_intent_client_secret") or ""),
            str(out.get("setup_intent_client_secret") or ""),
            str((chain or {}).get("setup_intent_client_secret") or ""),
            str((chain or {}).get("body_snippet") or ""),
            str(out.get("success_return_url") or ""),
            str(verification_url or ""),
            "\n".join(str(h.get("url") or "") for h in (out.get("hops") or [])),
        ]
    )
    setup_secret = (
        str(out.get("setup_intent_client_secret") or result.get("setup_intent_client_secret") or "").strip()
        or _extract_setup_intent_client_secret(secret_blob)
    )
    setup_id = str(out.get("setup_intent") or result.get("setup_intent") or "").strip() or _extract_setup_intent_id(secret_blob, setup_secret)
    if setup_secret:
        out["setup_intent_client_secret"] = setup_secret
    if setup_id:
        out["setup_intent"] = setup_id or out.get("setup_intent")

    # ---- Step 1c: SetupIntent terminal confirmation (成功.har B proof) ----
    if setup_id and setup_secret and not known_failed:
        pk = (chain.get("pk") if chain else "") or _extract_pk(secret_blob)
        seti_poll = poll_setup_intent(
            session,
            setup_intent=setup_id,
            client_secret=setup_secret,
            pk=pk or "",
            attempts=10,
            interval=1.5,
            log=log,
        )
        out["setup_intent_poll"] = seti_poll
        out["setup_intent_status"] = str(seti_poll.get("status") or "")
        if seti_poll.get("ok") or str(seti_poll.get("status") or "").lower() in {"succeeded", "success"}:
            out["notes"].append(f"setup_intent terminal status={out['setup_intent_status']} (B OK)")
            if out.get("redirect_status") in {"", "pending"}:
                out["redirect_status"] = "succeeded"
                out["notes"].append("promoted redirect_status=succeeded from setup_intent=succeeded")
        elif seti_poll.get("failed"):
            known_failed = True
            out["redirect_status"] = "failed"
            out["notes"].append(
                f"setup_intent terminal failed status={out['setup_intent_status'] or 'failed'}"
            )
            pay_poll_attempts = 0
            verify_attempts = min(int(verify_attempts or 16), 2)

    # ---- Step 1d: FORCE open success_return_url / checkout/verify ----
    force_verify = (
        str(out.get("success_return_url") or "").strip()
        or str(verification_url or "").strip()
        or str(result.get("verification_url") or "").strip()
    )
    if force_verify:
        verification_url = force_verify
        out["verification_url"] = force_verify
        out["success_return_url"] = out.get("success_return_url") or force_verify
        out["notes"].append(f"force success_return_url/verify (HTTP): {_scrub(force_verify)}")
        _log(log, f"[merchant] force open success_return_url via HTTP: {_scrub(force_verify)}")
        try:
            resp = session.get(force_verify, timeout=25, allow_redirects=True)
            final = str(resp.url or force_verify)
            if "chatgpt.com" in final and "checkout/verify" not in final:
                out["chatgpt_land_url"] = final
                out["verify_exit_detected"] = True
                out["notes"].append(f"left checkout/verify (HTTP) -> {_scrub(final)}")
            elif "checkout/verify" in final:
                out["processing_payment_seen"] = True
        except Exception as exc:
            out["notes"].append(f"force verify open failed: {exc}")

    # ---- Step 2: if on pay.openai pending, poll it (成功.har does many hits here) ----
    pay_url = ""
    if "pay.openai.com" in (final_redirect_url or ""):
        pay_url = final_redirect_url
    elif "pay.openai.com" in (return_url or ""):
        pay_url = return_url
    if pay_url and out.get("redirect_status") in {"", "pending"} and existing_redirect != "failed" and not known_failed and pay_poll_attempts > 0:
        pay_poll = poll_openai_pay_status(
            session,
            pay_url,
            attempts=pay_poll_attempts,
            interval=2.0,
            log=log,
        )
        out["pay_poll"] = pay_poll
        if pay_poll.get("redirect_status"):
            out["redirect_status"] = pay_poll["redirect_status"]
        if pay_poll.get("setup_intent"):
            out["setup_intent"] = pay_poll["setup_intent"] or out.get("setup_intent")
        if pay_poll.get("setup_intent_client_secret"):
            out["setup_intent_client_secret"] = (
                pay_poll["setup_intent_client_secret"] or out.get("setup_intent_client_secret")
            )
        if pay_poll.get("success_return_url"):
            out["success_return_url"] = pay_poll["success_return_url"]
            if not verification_url:
                verification_url = pay_poll["success_return_url"]
                out["verification_url"] = verification_url
        if pay_poll.get("url"):
            out["final_redirect_url"] = pay_poll["url"]
            final_redirect_url = pay_poll["url"]
        if pay_poll.get("cs_id"):
            out["cs_id"] = pay_poll["cs_id"] or out.get("cs_id")
        if pay_poll.get("pk"):
            out["pk"] = pay_poll["pk"] or out.get("pk")

    # ---- Step 3: optional payment_pages poll (成功.har hits /init) ----
    # Prefer live hop/cs from chain; also recover from pay.openai URL / success_return.
    cs_id = (
        str(out.get("cs_id") or "").strip()
        or (chain.get("cs_id") if chain else "")
        or _extract_cs_id(out.get("final_redirect_url") or "")
        or _extract_cs_id(verification_url or "")
        or _extract_cs_id(out.get("success_return_url") or "")
        or _extract_cs_id(return_url or "")
    )
    pk = (
        str(out.get("pk") or "").strip()
        or (chain.get("pk") if chain else "")
        or _extract_pk(secret_blob)
    )
    stripe_poll: dict[str, Any] = {}
    if cs_id and not known_failed:
        stripe_poll = poll_payment_pages(session, cs_id, pk=pk or "", attempts=6, interval=1.5, log=log)
    elif cs_id and known_failed:
        # One cheap probe only — do not loop payment_pages while B is already failed.
        stripe_poll = poll_payment_pages(session, cs_id, pk=pk or "", attempts=1, interval=0.5, log=log)
    if stripe_poll:
        out["stripe_poll"] = stripe_poll
        if stripe_poll.get("redirect_status"):
            out["redirect_status"] = stripe_poll["redirect_status"] or out.get("redirect_status")
        if stripe_poll.get("verification_url") and not verification_url:
            verification_url = stripe_poll["verification_url"]
            out["verification_url"] = verification_url
            out["success_return_url"] = out.get("success_return_url") or verification_url
        if stripe_poll.get("setup_intent"):
            out["setup_intent"] = stripe_poll["setup_intent"] or out.get("setup_intent")
        if stripe_poll.get("setup_intent_client_secret") and not out.get("setup_intent_client_secret"):
            out["setup_intent_client_secret"] = stripe_poll["setup_intent_client_secret"]
        if stripe_poll.get("pk"):
            out["pk"] = stripe_poll["pk"] or out.get("pk")
            pk = str(out.get("pk") or pk or "")

    # Late seti poll if secret only became available after pay/payment_pages hops
    if (
        not known_failed
        and not out.get("setup_intent_poll")
        and out.get("setup_intent")
        and out.get("setup_intent_client_secret")
    ):
        seti_poll = poll_setup_intent(
            session,
            setup_intent=str(out.get("setup_intent") or ""),
            client_secret=str(out.get("setup_intent_client_secret") or ""),
            pk=pk or "",
            attempts=8,
            interval=1.5,
            log=log,
        )
        out["setup_intent_poll"] = seti_poll
        out["setup_intent_status"] = str(seti_poll.get("status") or "")
        if seti_poll.get("ok") or str(seti_poll.get("status") or "").lower() in {"succeeded", "success"}:
            out["notes"].append(
                f"late setup_intent terminal status={out['setup_intent_status']} (B OK after CS poll)"
            )
            if out.get("redirect_status") in {"", "pending"}:
                out["redirect_status"] = "succeeded"
                out["notes"].append("promoted redirect_status=succeeded from late setup_intent=succeeded")
        elif seti_poll.get("failed"):
            known_failed = True
            out["redirect_status"] = "failed"
            out["notes"].append(
                f"late setup_intent terminal failed status={out['setup_intent_status'] or 'failed'}"
            )
            verify_attempts = min(int(verify_attempts or 16), 2)

    # ensure success_return / verification from any known field
    if not verification_url:
        if out.get("success_return_url"):
            verification_url = str(out["success_return_url"])
        elif final_redirect_url:
            qs = _qs(final_redirect_url)
            if qs.get("success_return_url"):
                verification_url = unquote(qs["success_return_url"])
        verification_url = verification_url or str(result.get("verification_url") or "").strip()
        out["verification_url"] = verification_url
    if verification_url and not out.get("success_return_url"):
        out["success_return_url"] = verification_url

    # ---- Step 4: force open callback URL (checkout/verify) + poll Processing payment ----
    if verification_url:
        out["notes"].append(f"opening callback/verify URL: {_scrub(verification_url)}")
        _log(log, f"[merchant] open callback URL (checkout/verify): {_scrub(verification_url)}")
        verify = poll_checkout_verify(
            session,
            verification_url,
            attempts=verify_attempts,
            interval=verify_interval,
            log=log,
            known_failed=known_failed,
        )
        out["verify"] = verify
        out["processing_payment_seen"] = bool(verify.get("processing_seen") or verify.get("state") == "processing")
        out["stuck_on_processing_payment"] = bool(verify.get("stuck_processing"))
        if verify.get("redirect_status"):
            out["redirect_status"] = verify["redirect_status"] or out.get("redirect_status")
        if verify.get("setup_intent"):
            out["setup_intent"] = verify["setup_intent"] or out.get("setup_intent")
        if verify.get("url"):
            if "checkout/verify" in str(verify["url"]):
                out["verification_url"] = verify["url"]
            elif "chatgpt.com" in str(verify["url"]):
                out["chatgpt_land_url"] = verify["url"]
        if out["processing_payment_seen"]:
            out["notes"].append(
                "saw Processing payment UI (checkout/verify). This is intermediate; not paid yet."
            )
        if out["stuck_on_processing_payment"]:
            out["notes"].append(
                "still on Processing payment after long poll — likely stuck "
                "(callback failed or session/auth missing)."
            )
    else:
        out["notes"].append("no verification_url/success_return_url after hops — cannot open Processing payment page")

    # ---- Step 4b: account-side Plus confirmation when we left verify / have cookies ----
    land_url_probe = str(out.get("chatgpt_land_url") or "")
    verify_state_probe = str((out.get("verify") or {}).get("state") or "")
    if (land_url_probe or verify_state_probe in {"landed", "likely_done"} or cookie_count or loaded) and not known_failed:
        account = confirm_account_plus(session, log=log)
        out["account_confirm"] = account
        if account.get("plus"):
            out["plus_confirmed"] = True
            out["chatgpt_land_url"] = out.get("chatgpt_land_url") or "https://chatgpt.com/"
            out["notes"].append(
                f"account-side Plus confirmed plan={account.get('plan') or 'plus'}"
            )
    if session_path:
        saved = persist_merchant_session(session, session_path)
        if saved:
            out["session_path"] = saved
            out["notes"].append(f"persisted merchant session -> {saved}")
            # Sidecar B-layer evidence next to session cookies (for full B→C replay).
            try:
                sidecar = Path(saved).with_name("b_layer_evidence.json")
                sidecar.write_text(
                    json.dumps(
                        {
                            "return_url": out.get("return_url") or return_url or "",
                            "final_redirect_url": out.get("final_redirect_url") or final_redirect_url or "",
                            "setup_intent": out.get("setup_intent") or "",
                            "setup_intent_client_secret": out.get("setup_intent_client_secret") or "",
                            "stripe_return_status": out.get("stripe_return_status") or "",
                            "success_return_url": out.get("success_return_url") or "",
                            "verification_url": out.get("verification_url") or verification_url or "",
                            "redirect_status": out.get("redirect_status") or "",
                            "setup_intent_status": out.get("setup_intent_status") or "",
                            "session_path": saved,
                            "protocol_mode": "http_only_full_protocol",
                            "session_cookies": _snapshot_session_cookies(session),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                out["b_layer_evidence_path"] = str(sidecar)
                out["notes"].append(f"persisted B-layer evidence -> {sidecar}")
            except Exception as exc:
                out["notes"].append(f"B-layer evidence sidecar failed: {exc}")

    out["session_cookies"] = _snapshot_session_cookies(session)

    # ---- Step 5: map settlement (strict paid rules, 成功.har calibrated) ----
    redirect_status = str(out.get("redirect_status") or existing_redirect or "").lower()
    verify_state = str((out.get("verify") or {}).get("state") or "")
    land_url = str(out.get("chatgpt_land_url") or "")
    stripe_return_status = str(out.get("stripe_return_status") or "").lower()
    setup_intent = str(out.get("setup_intent") or "")
    has_stripe_success = stripe_return_status == "success" or (
        "pm-redirects.stripe.com" in (return_url or "") and "status=success" in (return_url or "")
    )
    has_setup = bool(setup_intent)
    setup_intent_status = str(out.get("setup_intent_status") or "").lower()
    setup_intent_ok = setup_intent_status in {"succeeded", "success"} or bool((out.get("setup_intent_poll") or {}).get("ok"))
    plus_confirmed = bool(out.get("plus_confirmed"))
    stuck = bool(out.get("stuck_on_processing_payment"))
    processing_seen = bool(out.get("processing_payment_seen"))
    if setup_intent_ok and redirect_status in {"", "pending"}:
        redirect_status = "succeeded"
        out["redirect_status"] = "succeeded"

    if existing_redirect == "failed":
        redirect_status = "failed"
        out["redirect_status"] = "failed"

    if plus_confirmed and (has_stripe_success or setup_intent_ok or redirect_status in {"succeeded", "success", "pending", ""}):
        out["merchant_chain_status"] = "full_success_b_c"
        out["settlement_status"] = "confirmed"
        out["stuck_on_processing_payment"] = False
        out["notes"].append("Account-side Plus confirmed after merchant half-chain (BR-style C).")
    elif setup_intent_ok and (land_url or verify_state in {"landed", "likely_done"}):
        out["merchant_chain_status"] = "full_success_b_c"
        out["settlement_status"] = "confirmed"
        out["stuck_on_processing_payment"] = False
        out["notes"].append("setup_intent=succeeded + left Processing payment / chatgpt land.")
    elif redirect_status == "failed" or verify_state == "failed" or setup_intent_status in {"canceled", "cancelled", "requires_payment_method"}:
        out["merchant_chain_status"] = "callback_failed"
        out["settlement_status"] = "pending_verification"
        out["stuck_on_processing_payment"] = True
        out["notes"].append(
            "B layer failed (redirect_status=failed / setup_intent failed) or verify failed. "
            "Processing payment will not clear - terminal NOT paid. "
            "Action: stop waiting; auto card-retry / re-run BA with new funding."
        )
    elif stuck and not land_url and redirect_status not in {"succeeded", "success"}:
        # hard stuck on Processing payment
        if has_stripe_success and has_setup:
            out["merchant_chain_status"] = "stuck_processing_payment"
            out["settlement_status"] = "pending_verification"
            out["notes"].append(
                "Stuck on Processing payment after Stripe success return. "
                "C layer did not leave verify — terminal unpaid for this run. "
                "Action: do not wait; card-retry / re-run BA (session-less poll cannot finish Plus)."
            )
        else:
            out["merchant_chain_status"] = "stuck_processing_payment"
            out["settlement_status"] = "pending_verification"
            out["notes"].append(
                "Stuck on Processing payment without full B success signals. NOT paid."
            )
    elif has_stripe_success and (land_url or verify_state in {"landed", "likely_done"}):
        out["merchant_chain_status"] = "full_success_b_c"
        out["settlement_status"] = "confirmed"
        out["stuck_on_processing_payment"] = False
        out["notes"].append("Matched 成功.har B+C: Stripe return success + left Processing payment / chatgpt land.")
    elif redirect_status in {"succeeded", "success"} and verify_state in {"landed", "likely_done"}:
        out["merchant_chain_status"] = "full_success_b_c"
        out["settlement_status"] = "confirmed"
        out["stuck_on_processing_payment"] = False
        out["notes"].append("B+C completed: redirect_status=succeeded and verify landed.")
    elif has_stripe_success and has_setup and redirect_status in {"", "pending"}:
        if land_url:
            out["merchant_chain_status"] = "full_success_b_c"
            out["settlement_status"] = "confirmed"
            out["notes"].append(
                f"成功.har path: Stripe return success + setup_intent + chatgpt land "
                f"(redirect_status={redirect_status or 'pending'})."
            )
        elif processing_seen:
            out["merchant_chain_status"] = "processing_payment"
            out["settlement_status"] = "pending_verification"
            out["notes"].append(
                "On Processing payment (expected intermediate from 成功.har). Not paid until leave verify / land."
            )
        else:
            out["merchant_chain_status"] = "merchant_callback_ok_pending_ui"
            out["settlement_status"] = "pending_verification"
            out["notes"].append("B OK signals present; C still pending.")
    elif processing_seen or verify_state == "processing":
        out["merchant_chain_status"] = "processing_payment"
        out["settlement_status"] = "pending_verification"
        out["notes"].append("Processing payment page active — intermediate, not paid.")
    elif land_url:
        out["merchant_chain_status"] = "chatgpt_landed"
        out["settlement_status"] = "pending_verification"
        out["notes"].append("landed on chatgpt.com; awaiting confirmed settlement.")
    else:
        out["merchant_chain_status"] = "incomplete"
        if not out.get("settlement_status"):
            out["settlement_status"] = "authorization_only"
        out["notes"].append("merchant half-chain incomplete vs 成功.har.")

    # Terminal unpaid outcomes must not keep console in "wait Processing payment" loop.
    terminal_unpaid = out.get("merchant_chain_status") in {
        "callback_failed",
        "stuck_processing_payment",
        "incomplete",
        "no_urls",
    }
    out["terminal_unpaid"] = bool(terminal_unpaid and out.get("settlement_status") != "confirmed")
    out["should_stop_processing_wait"] = bool(
        out.get("merchant_chain_status") in {"callback_failed", "stuck_processing_payment"}
        or known_failed
    )
    out["card_retry_recommended"] = bool(
        out.get("merchant_chain_status") in {"callback_failed", "stuck_processing_payment"}
    )

    out["protocol_mode"] = "http_only_full_protocol"
    # Force-refresh B-layer evidence snapshot after all HTTP hops / polls.
    out["b_layer"] = {
        "return_url": out.get("return_url") or return_url or "",
        "final_redirect_url": out.get("final_redirect_url") or final_redirect_url or "",
        "setup_intent": out.get("setup_intent") or "",
        "setup_intent_client_secret": out.get("setup_intent_client_secret") or result.get("setup_intent_client_secret") or "",
        "stripe_return_status": out.get("stripe_return_status") or "",
        "session_path": out.get("session_path") or session_path or "",
        "session_cookies": out.get("session_cookies") or [],
        "redirect_status": out.get("redirect_status") or "",
        "success_return_url": out.get("success_return_url") or "",
        "verification_url": out.get("verification_url") or verification_url or "",
        "setup_intent_status": out.get("setup_intent_status") or "",
    }
    out["merged_result"] = {
        **result,
        "return_url": out.get("return_url") or return_url,
        "final_redirect_url": out.get("final_redirect_url") or final_redirect_url,
        "verification_url": out.get("verification_url") or verification_url,
        "success_return_url": out.get("success_return_url") or "",
        "redirect_status": out.get("redirect_status") or "",
        "setup_intent": out.get("setup_intent") or "",
        "stripe_return_status": out.get("stripe_return_status") or "",
        "settlement_status": out.get("settlement_status") or result.get("settlement_status") or "",
        "merchant_chain_status": out.get("merchant_chain_status"),
        "chatgpt_land_url": out.get("chatgpt_land_url") or "",
        "processing_payment_seen": out.get("processing_payment_seen"),
        "stuck_on_processing_payment": out.get("stuck_on_processing_payment"),
        "terminal_unpaid": out.get("terminal_unpaid"),
        "should_stop_processing_wait": out.get("should_stop_processing_wait"),
        "card_retry_recommended": out.get("card_retry_recommended"),
        "protocol_mode": "http_only_full_protocol",
        "verify_exit_detected": bool(out.get("verify_exit_detected")),
        "plus_confirmed": out.get("plus_confirmed"),
        "setup_intent_status": out.get("setup_intent_status") or "",
        "setup_intent_client_secret": out.get("setup_intent_client_secret") or result.get("setup_intent_client_secret") or "",
        "session_path": out.get("session_path") or "",
        "session_cookies": out.get("session_cookies") or [],
        "account_confirm": out.get("account_confirm"),
        "b_layer": out.get("b_layer") or {},
        "merchant_evidence_pre_path": out.get("merchant_evidence_pre_path") or "",
        "merchant_evidence_post_path": out.get("merchant_evidence_post_path") or "",
        "merchant_evidence_latest_path": out.get("merchant_evidence_latest_path") or "",
        "merchant_replay_input_path": out.get("merchant_replay_input_path") or "",
    }
    post_paths = persist_merchant_evidence(
        {**result, **out, "merged_result": out["merged_result"]},
        phase="post",
        session=session,
        session_path=out.get("session_path") or session_path,
    )
    if post_paths:
        out["merchant_evidence_post_path"] = post_paths.get("evidence_path", "")
        out["merchant_evidence_latest_path"] = post_paths.get("latest_path", "")
        out["merchant_replay_input_path"] = post_paths.get("replay_input_path", "")
        out["merged_result"]["merchant_evidence_pre_path"] = out.get("merchant_evidence_pre_path") or ""
        out["merged_result"]["merchant_evidence_post_path"] = out.get("merchant_evidence_post_path") or ""
        out["merged_result"]["merchant_evidence_latest_path"] = out.get("merchant_evidence_latest_path") or ""
        out["merged_result"]["merchant_replay_input_path"] = out.get("merchant_replay_input_path") or ""
        out["notes"].append(f"persisted merchant evidence (post) -> {out['merchant_evidence_post_path']}")
        _log(log, f"[merchant] evidence post: {out['merchant_evidence_post_path']}")
    return out
