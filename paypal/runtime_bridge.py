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
from paypal.runtime_config import (
    apply_runtime_to_environ,
    effective_browser_engine,
    has_roxy_key as _has_roxy_key_cfg,
    normalize_coarse_mode,
    resolve_runtime,
    resolve_and_apply,
)

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

from paypal.smsbower_countries import SMSBOWER_COUNTRY_IDS, resolve_smsbower_country_id



def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def resolve_runtime_mode(explicit: str | None = None) -> str:
    """Return one of: protocol | headless | auto | roxy."""
    return resolve_runtime(runtime_mode=explicit).runtime_mode
    if raw in {"headless", "playwright", "local_headless"}:
        return "headless"
    if raw in {"roxy"}:
        return "roxy"
    if raw in {"auto", "automatic"}:
        return "auto"
    return "protocol"


def has_roxy_key() -> bool:
    return _has_roxy_key_cfg()


def effective_browser_runtime(mode: str | None = None) -> str:
    """Concrete runtime engine: protocol | headless | roxy."""
    return effective_browser_engine(resolve_runtime_mode(mode))
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


def run_phase0_browser_assist(flow, page_url: str, *, force: bool = False, html: str = "", status_code: int = 0) -> dict[str, Any]:
    """Deep Phase0 DataDome assist aligned with openai-paypal BR package.

    - protocol mode: skip
    - headless: solve_datadome_with_local_headless, import cookies + datadome
    - roxy: solve_datadome_with_roxy when browser available, else capture profile
    - on 403 / authchallenge markers: always attempt solve when not protocol
    """
    mode = effective_browser_runtime(getattr(flow, "runtime_mode", None))
    result: dict[str, Any] = {"runtime": mode, "ok": False, "skipped": mode == "protocol", "reason": "phase0"}
    if mode == "protocol" and not force:
        return result

    proto = flow._ensure_protocol()
    profile = seed_browser_profile(proto)
    # keep module-level config profile roughly aligned for libraries that read it
    try:
        import config as cfg
        if hasattr(cfg, "BROWSER_PROFILE") and isinstance(cfg.BROWSER_PROFILE, dict):
            cfg.BROWSER_PROFILE.update(profile)
    except Exception:
        pass

    proxy_url = getattr(flow.proxy_config, "url", None)
    if hasattr(flow.session, "export_cookies_for_browser"):
        cookies = flow.session.export_cookies_for_browser()
    else:
        cookies = _session_cookies_list(flow.session)

    challenged = False
    lower = (html or "").lower()
    if status_code == 403 or "datadome" in lower or "captcha-delivery" in lower or "authchallenge" in lower:
        challenged = True
        result["challenged"] = True

    def _apply_solved(solved: dict[str, Any], runtime: str) -> dict[str, Any]:
        out = {"runtime": runtime, "ok": False, "skipped": False}
        if not isinstance(solved, dict):
            out["error"] = "empty solve result"
            return out
        out["detail"] = {
            k: solved.get(k)
            for k in ("ok", "status", "url", "error", "blocked_by_datadome", "datadome", "clientid")
            if k in solved
        }
        cookies_in = solved.get("cookies") or []
        n = 0
        if hasattr(flow.session, "import_browser_cookies"):
            n = flow.session.import_browser_cookies(cookies_in)
        else:
            n = _import_cookies_to_session(flow.session, cookies_in)
        out["cookies_imported"] = n
        datadome = str(solved.get("datadome") or "")
        if datadome:
            try:
                flow.state.datadome_cookie = datadome
            except Exception:
                pass
        clientid = str(solved.get("clientid") or "")
        if clientid:
            try:
                flow.state.datadome_clientid = clientid  # type: ignore[attr-defined]
            except Exception:
                pass
        ok = bool(solved.get("ok") or datadome or n > 0)
        out["ok"] = ok
        if ok:
            logger.info(
                "DataDome/browser Phase0 cleared via {} cookies={} datadome={}",
                runtime,
                n,
                bool(datadome),
            )
        else:
            logger.warning("DataDome/browser Phase0 did not clear via {} detail={}", runtime, out.get("detail"))
        return out

    try:
        if mode == "roxy" or (mode == "auto" and has_roxy_key()):
            try:
                from paypal.roxy_fingerprint import (
                    capture_roxy_runtime_profile,
                    solve_datadome_with_roxy,
                    load_roxy_capture_config,
                )
                # open/capture roxy browser first
                cap = capture_roxy_runtime_profile(proxy_url=proxy_url)
                roxy_browser = None
                if isinstance(cap, dict):
                    roxy_browser = cap.get("roxy_browser") or cap
                    if cap.get("cookies"):
                        if hasattr(flow.session, "import_browser_cookies"):
                            flow.session.import_browser_cookies(cap.get("cookies") or [])
                        else:
                            _import_cookies_to_session(flow.session, cap.get("cookies") or [])
                if challenged or force or True:
                    # always try solve on roxy path for phase0 assist
                    if roxy_browser and isinstance(roxy_browser, dict):
                        solved = solve_datadome_with_roxy(
                            roxy_browser,
                            page_url,
                            cookies=cookies,
                            wait_seconds=float(os.getenv("PAYPAL_DATADOME_ROXY_WAIT_SECONDS") or 12),
                        )
                        applied = _apply_solved(solved, "roxy")
                        applied["capture_ok"] = bool(cap)
                        return applied
                result["ok"] = bool(cap)
                result["capture"] = True
                return result
            except Exception as roxy_exc:
                logger.warning("Roxy Phase0 assist failed, trying headless: {}", roxy_exc)
                if resolve_runtime_mode(getattr(flow, "runtime_mode", None)) == "roxy":
                    # fall through to headless only for auto; for explicit roxy record error
                    if effective_browser_runtime(flow.runtime_mode) == "roxy" and not has_roxy_key():
                        pass
                # fallthrough headless

        from paypal.local_headless import solve_datadome_with_local_headless

        wait = float(os.getenv("PAYPAL_DATADOME_HEADLESS_WAIT_SECONDS") or 14)
        solved = solve_datadome_with_local_headless(
            page_url,
            cookies=cookies,
            wait_seconds=wait,
            proxy_url=proxy_url,
            browser_profile=profile,
        )
        return _apply_solved(solved if isinstance(solved, dict) else {}, "headless")
    except Exception as exc:
        logger.warning("Phase0 browser assist failed ({}): {}", mode, exc)
        result["error"] = str(exc)
        result["ok"] = False
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
    iso = (country_iso or "BR").upper()
    sid = resolve_smsbower_country_id(iso)
    try:
        provider.country = str(sid)
        logger.info("SMSBower country mapping {} -> id {}", iso, sid)
    except Exception:
        pass
    return provider


def reserve_smsbower_number(flow) -> dict[str, Any]:
    """Reserve SMSBower number, update flow.user phone, return public info."""
    provider = getattr(flow, "_otp_provider", None)
    if provider is None:
        return {"ok": False, "error": "SMSBower not enabled"}
    iso = flow._ensure_protocol().code
    provider.country = resolve_smsbower_country_id(iso)
    activation = provider.reserve_number()
    # normalize to e164 for protocol country
    phone_raw = getattr(activation, "phone_number", "") or ""
    digits = "".join(ch for ch in str(phone_raw) if ch.isdigit())
    e164 = phone_raw if str(phone_raw).startswith("+") else ("+" + digits)
    try:
        flow._update_user_phone(e164)
    except Exception as exc:
        logger.warning("SMSBower phone normalize failed ({}): {} raw={}", iso, exc, phone_raw)
    flow._smsbower_activation = activation
    try:
        from paypal.smsbower import activation_to_public_dict
        pub = activation_to_public_dict(activation)
    except Exception:
        pub = {"activation_id": getattr(activation, "activation_id", ""), "phone_number": e164[-4:].rjust(8, "*")}
    logger.info("SMSBower reserved number for {} -> {}", iso, pub.get("phone_number"))
    return {"ok": True, "activation": pub, "phone": flow.user.phone}

