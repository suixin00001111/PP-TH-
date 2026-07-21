"""Browser + protocol runtime bridge (openai-paypal style, multi-country aware).

Runtime modes exposed to UI/CLI:
  - protocol: pure HTTP (existing multi-country flow)
  - headless: Playwright Chromium assists DataDome / fingerprint / MTR
  - auto: prefer Roxy if API key present, else headless, else protocol

SMSBower auto-OTP coexists with manual OTP submission on Web.
"""
from __future__ import annotations

import os
from typing import Any

from loguru import logger

from paypal.protocol import ProtocolContext, build_protocol

# Timezone hints for major markets (browser profile must match protocol country)
_TZ: dict[str, tuple[str, int]] = {
    "TH": ("Asia/Bangkok", -420),
    "JP": ("Asia/Tokyo", -540),
    "KR": ("Asia/Seoul", -540),
    "CN": ("Asia/Shanghai", -480),
    "HK": ("Asia/Hong_Kong", -480),
    "TW": ("Asia/Taipei", -480),
    "SG": ("Asia/Singapore", -480),
    "MY": ("Asia/Kuala_Lumpur", -480),
    "ID": ("Asia/Jakarta", -420),
    "VN": ("Asia/Ho_Chi_Minh", -420),
    "PH": ("Asia/Manila", -480),
    "IN": ("Asia/Kolkata", -330),
    "AE": ("Asia/Dubai", -240),
    "SA": ("Asia/Riyadh", -180),
    "IL": ("Asia/Jerusalem", -120),
    "TR": ("Europe/Istanbul", -180),
    "RU": ("Europe/Moscow", -180),
    "GB": ("Europe/London", 0),
    "IE": ("Europe/Dublin", 0),
    "PT": ("Europe/Lisbon", 0),
    "DE": ("Europe/Berlin", -60),
    "FR": ("Europe/Paris", -60),
    "ES": ("Europe/Madrid", -60),
    "IT": ("Europe/Rome", -60),
    "NL": ("Europe/Amsterdam", -60),
    "BE": ("Europe/Brussels", -60),
    "CH": ("Europe/Zurich", -60),
    "AT": ("Europe/Vienna", -60),
    "SE": ("Europe/Stockholm", -60),
    "NO": ("Europe/Oslo", -60),
    "DK": ("Europe/Copenhagen", -60),
    "FI": ("Europe/Helsinki", -120),
    "PL": ("Europe/Warsaw", -60),
    "US": ("America/New_York", 300),
    "CA": ("America/Toronto", 300),
    "MX": ("America/Mexico_City", 360),
    "BR": ("America/Sao_Paulo", 180),
    "AR": ("America/Argentina/Buenos_Aires", 180),
    "CL": ("America/Santiago", 240),
    "CO": ("America/Bogota", 300),
    "PE": ("America/Lima", 300),
    "AU": ("Australia/Sydney", -600),
    "NZ": ("Pacific/Auckland", -720),
    "ZA": ("Africa/Johannesburg", -120),
}

# SMSBower platform country ids (subset; override with SMSBOWER_COUNTRY / job field)
SMSBOWER_COUNTRY_IDS: dict[str, str] = {
    "BR": "73",
    "US": "12",  # common mapping may vary by provider — override via env
    "GB": "16",
    "TH": "52",
    "ID": "6",
    "PH": "4",
    "IN": "22",
    "MX": "54",
    "JP": "182",
}


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def resolve_runtime_mode(explicit: str | None = None) -> str:
    """Return one of: protocol | headless | auto (roxy is selected inside auto/headless path)."""
    raw = (explicit or _env("PAYPAL_RUNTIME_MODE") or _env("RUNTIME_MODE") or "").strip().lower()
    if not raw:
        try:
            from config import RUNTIME_MODE as cfg_mode
            raw = str(cfg_mode or "protocol").strip().lower()
        except Exception:
            raw = "protocol"
    if raw in {"protocol", "http", "pure"}:
        return "protocol"
    if raw in {"headless", "playwright", "local_headless"}:
        return "headless"
    if raw in {"roxy"}:
        return "roxy"
    if raw in {"auto", "automatic"}:
        return "auto"
    return "protocol"


def has_roxy_key() -> bool:
    key = _env("PAYPAL_ROXY_API_KEY") or _env("ROXY_API_KEY")
    if key:
        return True
    try:
        from config import ROXY_API_KEY
        return bool(str(ROXY_API_KEY or "").strip())
    except Exception:
        return False


def effective_browser_runtime(mode: str | None = None) -> str:
    """Concrete runtime engine: protocol | headless | roxy."""
    m = resolve_runtime_mode(mode)
    if m == "protocol":
        return "protocol"
    if m == "roxy":
        return "roxy" if has_roxy_key() else "headless"
    if m == "headless":
        return "headless"
    # auto
    if has_roxy_key():
        return "roxy"
    return "headless"


def seed_browser_profile(protocol: ProtocolContext | str) -> dict[str, Any]:
    """Build country-aligned browser profile for headless/roxy (not hard-coded BR)."""
    if not isinstance(protocol, ProtocolContext):
        protocol = build_protocol(str(protocol))
    try:
        from config import BROWSER_PROFILE, USER_AGENT
        base = dict(BROWSER_PROFILE)
        ua = USER_AGENT
    except Exception:
        base = {}
        ua = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        )
    tz_name, tz_off = _TZ.get(protocol.code, ("UTC", 0))
    base.update(
        {
            "country": protocol.code,
            "language": protocol.locale_bcp47,
            "locale": protocol.locale_tag,
            "timezone": tz_name,
            "timezone_offset_minutes": tz_off,
            "timezone_offset_ms": tz_off * 60 * 1000,
            "user_agent": ua,
            "fingerprint_source": effective_browser_runtime(),
        }
    )
    return base


def _session_cookies_list(session) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        jar = session.client.cookies
        # curl_cffi / requests style
        for c in jar:
            name = getattr(c, "name", None) or (c[0] if isinstance(c, (list, tuple)) else None)
            value = getattr(c, "value", None) or (c[1] if isinstance(c, (list, tuple)) and len(c) > 1 else None)
            if not name:
                continue
            item = {
                "name": str(name),
                "value": str(value or ""),
                "domain": getattr(c, "domain", ".paypal.com") or ".paypal.com",
                "path": getattr(c, "path", "/") or "/",
            }
            out.append(item)
    except Exception as exc:
        logger.debug("cookie export failed: {}", exc)
    return out


def _import_cookies_to_session(session, cookies: list[dict[str, Any]] | None) -> int:
    if not cookies:
        return 0
    n = 0
    for c in cookies:
        try:
            name = str(c.get("name") or "")
            value = str(c.get("value") or "")
            if not name:
                continue
            domain = str(c.get("domain") or ".paypal.com")
            path = str(c.get("path") or "/")
            session.client.cookies.set(name, value, domain=domain, path=path)
            n += 1
        except Exception:
            continue
    return n


def run_phase0_browser_assist(flow, page_url: str) -> dict[str, Any]:
    """Optional DataDome/browser assist for Phase 0. Returns result dict."""
    mode = effective_browser_runtime(getattr(flow, "runtime_mode", None))
    result: dict[str, Any] = {"runtime": mode, "ok": False, "skipped": mode == "protocol"}
    if mode == "protocol":
        return result

    proto = flow._ensure_protocol()
    profile = seed_browser_profile(proto)
    proxy_url = getattr(flow.proxy_config, "url", None)
    cookies = _session_cookies_list(flow.session)

    try:
        if mode == "roxy":
            # Roxy path: capture profile + optional datadome via phase1-like open
            from paypal.roxy_fingerprint import capture_roxy_runtime_profile

            cap = capture_roxy_runtime_profile(proxy_url=proxy_url, seed_profile=profile)
            result["ok"] = bool(cap)
            result["capture"] = {k: cap.get(k) for k in ("ok", "runtime", "error") if isinstance(cap, dict)}
            if isinstance(cap, dict) and cap.get("cookies"):
                n = _import_cookies_to_session(flow.session, cap.get("cookies") or [])
                result["cookies_imported"] = n
            return result

        # headless
        from paypal.local_headless import solve_datadome_with_local_headless

        solved = solve_datadome_with_local_headless(
            page_url,
            cookies=cookies,
            wait_seconds=12.0,
            proxy_url=proxy_url,
            browser_profile=profile,
        )
        result["ok"] = bool(solved and (solved.get("ok") or solved.get("datadome") or solved.get("cookies")))
        if isinstance(solved, dict) and solved.get("cookies"):
            n = _import_cookies_to_session(flow.session, solved.get("cookies") or [])
            result["cookies_imported"] = n
        result["detail"] = {
            k: solved.get(k)
            for k in ("ok", "runtime", "status", "error", "final_url")
            if isinstance(solved, dict) and k in solved
        }
        return result
    except Exception as exc:
        logger.warning("Phase0 browser assist failed ({}): {}", mode, exc)
        result["error"] = str(exc)
        if resolve_runtime_mode(getattr(flow, "runtime_mode", None)) != "auto":
            # non-auto: surface soft-fail, flow continues with protocol
            pass
        return result


def run_phase1_browser_assist(flow, page_url: str) -> dict[str, Any]:
    """Optional browser risk + MTR for Phase 1."""
    mode = effective_browser_runtime(getattr(flow, "runtime_mode", None))
    result: dict[str, Any] = {"runtime": mode, "ok": False, "skipped": mode == "protocol"}
    if mode == "protocol":
        return result

    proto = flow._ensure_protocol()
    profile = seed_browser_profile(proto)
    proxy_url = getattr(flow.proxy_config, "url", None)
    cookies = _session_cookies_list(flow.session)
    ba = getattr(flow, "ba_token", "") or ""

    try:
        if mode == "roxy":
            from paypal.roxy_fingerprint import run_phase1_risk_with_roxy_browser

            raw = run_phase1_risk_with_roxy_browser(
                page_url,
                cookies=cookies,
                proxy_url=proxy_url,
                browser_profile=profile,
                correlation_id=ba,
            )
        else:
            from paypal.local_headless import run_phase1_risk_with_local_headless

            raw = run_phase1_risk_with_local_headless(
                page_url,
                cookies=cookies,
                proxy_url=proxy_url,
                browser_profile=profile,
                correlation_id=ba,
            )
        result["ok"] = bool(raw)
        if isinstance(raw, dict):
            if raw.get("cookies"):
                result["cookies_imported"] = _import_cookies_to_session(flow.session, raw.get("cookies") or [])
            result["detail"] = {k: raw.get(k) for k in ("ok", "runtime", "error", "mtr") if k in raw}
        # best-effort MTR protocol path as supplement
        try:
            from paypal.mtr import extract_mtr_config, extract_dfp_script_url, ensure_mtr_config, send_mtr_signals

            # state-like namespace for mtr helpers
            class _S:
                pass

            st = flow.state
            html = ""
            ensure_mtr_config(st, page_url=page_url)
            send_mtr_signals(flow.session, st, page_url=page_url)
            result["mtr_protocol"] = True
        except Exception as mtr_exc:
            logger.debug("MTR protocol supplement skipped: {}", mtr_exc)
            result["mtr_protocol"] = False
        return result
    except Exception as exc:
        logger.warning("Phase1 browser assist failed ({}): {}", mode, exc)
        result["error"] = str(exc)
        return result


def build_otp_provider(*, enabled: bool | None, api_key: str | None, country_iso: str):
    """Build SMSBower provider if enabled; else None (manual OTP)."""
    try:
        from paypal.smsbower import build_smsbower_provider, SMSBowerOtpProvider
    except Exception as exc:
        logger.warning("SMSBower module unavailable: {}", exc)
        return None
    provider = build_smsbower_provider(enabled=enabled, api_key=api_key)
    if provider is None:
        return None
    # map ISO country to SMSBower numeric id when possible
    iso = (country_iso or "BR").upper()
    sid = (
        os.getenv("SMSBOWER_COUNTRY")
        or os.getenv("PAYPAL_SMSBOWER_COUNTRY")
        or SMSBOWER_COUNTRY_IDS.get(iso)
        or getattr(provider, "country", "73")
    )
    try:
        provider.country = str(sid)
    except Exception:
        pass
    return provider
