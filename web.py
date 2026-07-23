#!/usr/bin/env python3
"""Local web UI for the PayPal Billing Agreement flow.

Run:
    python web.py --host 127.0.0.1 --port 8080
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from loguru import logger

from paypal.flow import PayPalFlow
from paypal.models import BillingAddress, CardInfo, UserInfo
from paypal.oaipy_data import generate_address, generate_card, generate_user
from paypal.proxy import ProxyConfig, build_proxy_config, resolve_working_proxy_entry, resolve_outbound_proxy, get_system_proxy_entry, scrub_process_proxy_env, restore_process_proxy_env
from paypal.regions import get_region, normalize_phone, normalize_region, list_regions_public
from paypal.b_layer_handoff import build_b_layer_evidence, persist_b_layer_evidence
from paypal.merchant_complete import complete_merchant_chain
from paypal.layer_status import annotate_layer_status
from paypal.region_matrix import list_matrix_public
from paypal.runtime_config import resolve_and_apply, resolve_runtime

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "web_static"



def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = os.getenv(name, "")
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(min_value, min(value, max_value))


PRODUCTION_MODE = env_bool("PAYPAL_WEB_PRODUCTION", False)
MAX_LOG_LINES = env_int("PAYPAL_WEB_MAX_LOG_LINES", 300, 50, 2000)
MAX_TOTAL_JOBS = env_int("PAYPAL_WEB_MAX_TOTAL_JOBS", 200, 10, 5000)
MAX_ACTIVE_JOBS = env_int("PAYPAL_WEB_MAX_ACTIVE_JOBS", 4, 1, 100)
MAX_ACTIVE_JOBS_PER_DEVICE = env_int("PAYPAL_WEB_MAX_ACTIVE_JOBS_PER_DEVICE", 2, 1, 20)
JOB_RETENTION_SECONDS = env_int("PAYPAL_WEB_JOB_RETENTION_SECONDS", 24 * 60 * 60, 60, 30 * 24 * 60 * 60)
OTP_INPUT_TIMEOUT_SECONDS = env_int("PAYPAL_WEB_OTP_TIMEOUT_SECONDS", 30 * 60, 60, 24 * 60 * 60)
ALLOW_DEBUG_LOGS = env_bool("PAYPAL_WEB_ALLOW_DEBUG_LOGS", False)
COOKIE_SECURE = env_bool("PAYPAL_WEB_COOKIE_SECURE", False)
DEVICE_COOKIE_NAME = "paypal_web_device_id"
DEVICE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
DEVICE_ID_RE = re.compile(r"^[a-f0-9]{32}$")
BA_TOKEN_RE = re.compile(r"^BA-[A-Za-z0-9]{8,80}$")

FINGERPRINT_SOURCE_CHOICES = {
    "random", "program", "python", "synthetic", "roxy", "browser",
    "headless", "local_headless", "playwright", "local_playwright", "auto",
}
DATADOME_MODE_CHOICES = {
    "protocol", "edge", "roxy", "browser", "headless", "local_headless",
    "playwright", "local_playwright", "auto", "off",
}
MTR_RUNTIME_CHOICES = {
    "python_generated", "python", "protocol", "roxy", "browser", "headless",
    "local_headless", "playwright", "local_playwright", "auto", "block", "off",
}
BUYER_IDENTITY_MODE_CHOICES = {
    "legacy", "original", "default", "classic", "v1", "phase4",
    "elevate_bind", "guest_elevate", "bind_ec", "elevate", "guest_bind", "bind", "v2",
    "elevate_guest_bind_ec",
}


RISK_SIGNALS_MODE_CHOICES = {
    "protocol", "python", "synthetic", "template", "roxy", "browser", "headless",
    "local_headless", "playwright", "local_playwright", "auto", "off",
}
ROXY_LIKE_MODE_VALUES = {
    "roxy", "browser", "real_browser", "chrome", "chromium", "roxy_browser", "roxybrowser",
}


def roxy_modes_need_key(*modes: object) -> bool:
    """True when any fine-knob selects Roxy or auto (needs Local API key)."""
    for mode in modes:
        value = str(mode or "").strip().lower().replace("-", "_")
        if value in ROXY_LIKE_MODE_VALUES or value == "auto":
            return True
    return False


def apply_web_roxy_config(
    *,
    roxy_api_key: str = "",
    roxy_api_host: str = "127.0.0.1",
    roxy_api_port: int | str = 50000,
    roxy_headless: bool = True,
    roxy_workspace_id: str = "",
    roxy_project_id: str = "",
) -> None:
    """Push Web UI Roxy settings into process env for paypal.roxy_fingerprint."""
    key = (roxy_api_key or "").strip()
    host = (roxy_api_host or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int(roxy_api_port or 50000)
    except Exception:
        port = 50000
    port = max(1, min(port, 65535))
    workspace_id = str(roxy_workspace_id or "").strip()
    project_id = str(roxy_project_id or "").strip()

    if key:
        os.environ["PAYPAL_ROXY_API_KEY"] = key
        os.environ["ROXY_API_KEY"] = key
    os.environ["PAYPAL_ROXY_API_HOST"] = host
    os.environ["ROXY_API_HOST"] = host
    os.environ["PAYPAL_ROXY_API_PORT"] = str(port)
    os.environ["ROXY_API_PORT"] = str(port)
    os.environ["PAYPAL_ROXY_HEADLESS"] = "1" if roxy_headless else "0"
    os.environ["ROXY_HEADLESS"] = "1" if roxy_headless else "0"
    if workspace_id:
        os.environ["PAYPAL_ROXY_WORKSPACE_ID"] = workspace_id
        os.environ["ROXY_WORKSPACE_ID"] = workspace_id
    else:
        os.environ.pop("PAYPAL_ROXY_WORKSPACE_ID", None)
    if project_id:
        os.environ["PAYPAL_ROXY_PROJECT_ID"] = project_id
        os.environ["ROXY_PROJECT_ID"] = project_id
    else:
        os.environ.pop("PAYPAL_ROXY_PROJECT_ID", None)


def test_roxy_connectivity(
    *,
    roxy_api_key: str,
    roxy_api_host: str = "127.0.0.1",
    roxy_api_port: int | str = 50000,
    roxy_headless: bool = True,
    roxy_workspace_id: str = "",
    roxy_project_id: str = "",
) -> dict[str, Any]:
    """Probe RoxyBrowser Local API (/browser/workspace)."""
    key = (roxy_api_key or "").strip()
    if not key:
        raise ValueError("缺少 Roxy API Key")
    host = (roxy_api_host or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int(roxy_api_port or 50000)
    except Exception:
        port = 50000
    port = max(1, min(port, 65535))
    apply_web_roxy_config(
        roxy_api_key=key,
        roxy_api_host=host,
        roxy_api_port=port,
        roxy_headless=bool(roxy_headless),
        roxy_workspace_id=roxy_workspace_id,
        roxy_project_id=roxy_project_id,
    )

    import urllib.error
    import urllib.request

    url = f"http://{host}:{port}/browser/workspace?page_index=1&page_size=5"
    req = urllib.request.Request(
        url,
        headers={
            "token": key,
            "Authorization": f"Bearer {key}",
            "api-key": key,
            "User-Agent": "pp-th-web-roxy-test",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            raw = resp.read(4000)
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            body = ""
        return {
            "ok": False,
            "message": f"Roxy 返回 HTTP {exc.code} ({host}:{port})" + (f" — {body}" if body else ""),
            "status": int(exc.code or 0),
            "host": host,
            "port": port,
        }
    except Exception as exc:
        return {
            "ok": False,
            "message": f"连接失败 {host}:{port} — {exc}",
            "host": host,
            "port": port,
        }

    text = raw.decode("utf-8", errors="replace")
    snippet = text[:160]
    workspace_count = 0
    first_workspace_id = ""
    first_project_id = ""
    try:
        payload = json.loads(text)
        data = payload.get("data") if isinstance(payload, dict) else None
        rows = []
        if isinstance(data, dict):
            rows = data.get("rows") or data.get("list") or []
        elif isinstance(data, list):
            rows = data
        if isinstance(rows, list):
            workspace_count = len(rows)
            if rows and isinstance(rows[0], dict):
                first_workspace_id = str(rows[0].get("id") or rows[0].get("workspaceId") or "")
                details = rows[0].get("project_details") or rows[0].get("projects") or []
                if isinstance(details, list) and details and isinstance(details[0], dict):
                    first_project_id = str(details[0].get("projectId") or details[0].get("id") or "")
        code = payload.get("code") if isinstance(payload, dict) else None
        if code not in (None, 0, "0"):
            msg = str(payload.get("msg") or payload.get("message") or snippet)
            if str(code) in {"403", "401"} or "token" in msg.lower() or "验证" in msg:
                tip = "API Key 不正确或已失效，请到 Roxy「设置 → API」复制最新 Key，并确认 Local API 已开启"
                return {
                    "ok": False,
                    "message": tip + f"（{msg}）",
                    "status": status,
                    "host": host,
                    "port": port,
                    "snippet": snippet,
                }
            return {
                "ok": False,
                "message": f"Roxy 业务码 {code}: {msg}",
                "status": status,
                "host": host,
                "port": port,
                "snippet": snippet,
            }
    except Exception:
        pass

    hint = ""
    if workspace_count:
        hint = f"，检测到 {workspace_count} 个工作区"
        if first_workspace_id:
            hint += f"（示例 workspace={first_workspace_id}"
            if first_project_id:
                hint += f", project={first_project_id}"
            hint += "）"
        hint += "；工作区/项目可留空由程序自动选"
    return {
        "ok": True,
        "message": f"Local API 可达 HTTP {status} ({host}:{port}){hint}",
        "status": status,
        "host": host,
        "port": port,
        "workspace_count": workspace_count,
        "sample_workspace_id": first_workspace_id,
        "sample_project_id": first_project_id,
        "snippet": snippet,
    }




def implicit_risk_signals_mode(
    fingerprint_source: object,
    datadome_mode: object,
    mtr_runtime: object,
    explicit: object = "",
) -> str:
    """Align with openai-paypal: derive risk mode from the three runtime knobs."""
    value = str(explicit or "").strip().lower().replace("-", "_")
    if value:
        return value
    modes = {
        str(fingerprint_source or "").strip().lower().replace("-", "_"),
        str(datadome_mode or "").strip().lower().replace("-", "_"),
        str(mtr_runtime or "").strip().lower().replace("-", "_"),
    }
    if modes & ROXY_LIKE_MODE_VALUES:
        return "roxy"
    if "auto" in modes:
        return "auto"
    if "protocol" in modes or "python_generated" in modes or "python" in modes:
        return "protocol"
    return "headless"


def derive_runtime_mode(fingerprint_source: str, datadome_mode: str, mtr_runtime: str) -> str:
    """Coarse runtime for browser engine selection (Brazil uses fine knobs primarily)."""
    modes = {
        str(fingerprint_source or "").strip().lower().replace("-", "_"),
        str(datadome_mode or "").strip().lower().replace("-", "_"),
        str(mtr_runtime or "").strip().lower().replace("-", "_"),
    }
    if modes & ROXY_LIKE_MODE_VALUES:
        return "roxy"
    if "auto" in modes:
        return "auto"
    if modes <= {"protocol", "edge", "python_generated", "python", "random", "program", "synthetic", "off", "block", ""}:
        # pure protocol / template path when DD protocol and no browser engine requested
        if "protocol" in modes or "edge" in modes:
            return "protocol"
    return "headless"


TH_MOBILE_RE = re.compile(r"^[689]\d{8}$")

ACTIVE_STATUSES = {"queued", "running", "awaiting_otp"}
RUNNER_SEMAPHORE = threading.BoundedSemaphore(MAX_ACTIVE_JOBS)
RATE_LOCK = threading.RLock()
RATE_BUCKETS: dict[tuple[str, str], list[float]] = {}


# ----------------------------- helpers -----------------------------


def now_ts() -> float:
    return time.time()


def normalize_thailand_phone(value: str) -> str:
    e164, _, _ = normalize_phone("TH", value)
    return e164


def normalize_region_phone(country: str, value: str) -> str:
    e164, _, _ = normalize_phone(country, value)
    return e164


def mask_middle(value: str, left: int = 6, right: int = 4) -> str:
    value = value or ""
    if len(value) <= left + right:
        return "***" if value else ""
    return f"{value[:left]}…{value[-right:]}"


def mask_card(number: str) -> str:
    digits = "".join(ch for ch in (number or "") if ch.isdigit())
    if len(digits) <= 4:
        return "••••"
    grouped = " ".join([digits[i : i + 4] for i in range(0, len(digits), 4)])
    return f"•••• •••• •••• {grouped[-4:]}"


def mask_email(value: str) -> str:
    if "@" not in (value or ""):
        return "***"
    local, domain = value.split("@", 1)
    if len(local) <= 2:
        return f"{local[:1]}***@{domain}"
    return f"{local[:2]}***{local[-1:]}@{domain}"


def mask_digits(value: str, keep: int = 4) -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if not digits:
        return ""
    if len(digits) <= keep:
        return "*" * len(digits)
    return f"{'*' * (len(digits) - keep)}{digits[-keep:]}"


def mask_phone(value: str) -> str:
    return mask_digits(value, keep=4)


def phone_input_hint(country: str, current_phone: str = "") -> str:
    """OTP/phone prompt without full phone digits (avoids redact_text masking examples)."""
    try:
        region = get_region(country)
        cc = str(getattr(region, "phone_cc", "") or "").strip()
    except Exception:
        cc = ""
    if cc and not str(cc).startswith("+"):
        cc = f"+{cc}"
    current = mask_phone(current_phone) if current_phone else ""
    if current:
        return (
            f"当前号码 {current}。"
            f"请填【另一号码】：国家码 {cc or '+??'} + 本地号"
            f"（不要默认再填同一号码，除非确认该号可用）"
        )
    return f"格式：国家码 {cc or '+??'} + 本地号"


def redact_text(value: Any) -> str:
    """Best-effort redaction for logs/UI errors. Keep status information, hide secrets/PII."""
    text = str(value or "")
    if not text:
        return text

    # URL query parameters and JSON-ish key/value pairs.
    text = re.sub(
        r"(?i)([?&](?:ba_token|token|ec_token|billingAgreementId|access_token|code|pin|password|otp)=)([^&\s\"']+)",
        lambda m: f"{m.group(1)}{mask_middle(m.group(2), 4, 4)}",
        text,
    )
    text = re.sub(
        r"(?i)(\b(?:ba_token|ec_token|billingAgreementId|token|accessToken|password|securityCode|cvv|pin|otp)\b\s*[:=]\s*)([\"']?)([^&,\"'\s}{]+)([\"']?)",
        lambda m: f"{m.group(1)}{m.group(2)}<redacted>{m.group(4)}",
        text,
    )

    # Common token formats.
    text = re.sub(r"\bBA-[A-Za-z0-9]{8,80}\b", lambda m: mask_middle(m.group(0), 4, 4), text)
    text = re.sub(r"\bEC-[A-Za-z0-9]{8,80}\b", lambda m: mask_middle(m.group(0), 4, 4), text)

    # Email, CPF, card-like long digit sequences, Thailand/international phone-like values.
    text = re.sub(
        r"\b([A-Za-z0-9._%+\-]{1,64})@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b",
        lambda m: mask_email(m.group(0)),
        text,
    )
    text = re.sub(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", "<redacted-cpf>", text)
    text = re.sub(
        r"(?<!\w)(?:\d[ -]?){13,19}(?!\w)",
        lambda m: mask_digits(m.group(0), keep=4),
        text,
    )
    text = re.sub(
        r"(?<!\w)\+?\d[\d(). -]{7,18}\d(?!\w)",
        lambda m: mask_phone(m.group(0)),
        text,
    )
    return text


def sanitize_payload(value: Any, key: str = "") -> Any:
    """Redact sensitive values before returning API payloads to the browser."""
    compact_key = key.lower().replace("_", "").replace("-", "")
    if compact_key in {"cookies", "sessioncookies", "merchantcookies"}:
        return "<redacted>"
    if isinstance(value, dict):
        return {k: sanitize_payload(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_payload(item, key) for item in value]
    if not isinstance(value, str):
        return value

    if compact_key in {"password", "securitycode", "cvv", "pin", "otp", "authorization", "cookie", "accesstoken"}:
        return "<redacted>"
    if compact_key in {"token", "batoken", "ectoken", "billingagreementid", "billingagreementtoken"}:
        return mask_middle(value, 4, 4)
    if compact_key in {"cardnumber", "encryptednumber"}:
        return mask_digits(value, keep=4)
    if compact_key in {"national_id", "identitydocument", "document"}:
        return "<redacted>"
    if compact_key == "email":
        return mask_email(value)
    if compact_key in {"phonenumber", "phone", "number", "phonelocal"} and sum(ch.isdigit() for ch in value) >= 8:
        return mask_phone(value)
    if compact_key.endswith("url") or compact_key in {"href", "referer", "location"}:
        return truncate_text(redact_text(value))
    return truncate_text(redact_text(value))


def truncate_text(value: str, max_chars: int = 1000) -> str:
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}…<truncated>"


def safe_result_payload(value: Any) -> Any:
    sanitized = sanitize_payload(value)
    if isinstance(sanitized, dict) and "raw_response" in sanitized:
        sanitized["raw_response"] = "<redacted>"
    return sanitized


def parse_cookie_header(header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in (header or "").split(";"):
        key, _, value = part.strip().partition("=")
        if key:
            cookies[key] = value
    return cookies


def public_generated_payload(user: UserInfo, card: CardInfo, address: BillingAddress) -> dict[str, Any]:
    """Data shown in the browser. Keep secrets/PII masked in API responses."""
    return {
        "user": {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": mask_email(user.email),
            "phone": mask_phone(user.phone),
            "phone_country_code": user.phone_country_code,
            "phone_local": mask_phone(user.phone_local),
            "password": "<redacted>",
            "dob": "<redacted>",
            "national_id": "<redacted>",
        },
        "card": {
            "number": mask_card(card.number),
            "expiry": card.expiry,
            "cvv": "***",
            "card_type": card.card_type,
        },
        "address": sanitize_payload(asdict(address)),
    }



def classify_proxy_transport_error(msg: str, body: str = "") -> str:
    """Map curl/proxy transport failures to actionable Chinese guidance."""
    text = f"{msg}\n{body}".strip()
    low = text.lower()
    m = re.search(r"forbidden\s+ip\s*=\s*([0-9.]+)\s*not supported", text, re.I)
    if m:
        return (
            f"代理拒绝当前公网 IP {m.group(1)}（not supported）。"
            "直连 cliproxy 被拒，但开 TUN 往往能通：TUN 改变了出口路径。"
            "处理：1) 清空代理输入框并开启系统 TUN；"
            "2) 或在 cliproxy 后台把该 IP 加入白名单后再填自定义代理；"
            "3) 不要同时开 TUN 又填 cliproxy（容易双层代理/超时）。"
        )
    if "forbidden ip" in low or ("not supported" in low and "ip" in low):
        return (
            f"代理拒绝当前接入 IP。原始信息：{text[:180]}。"
            "请到代理商后台检查 IP 白名单/套餐权限。"
        )
    if "connect tunnel failed" in low and "403" in low:
        return (
            "代理 CONNECT 返回 403。常见原因：账号错误或当前 IP 被代理商拒绝。"
            f" 原始：{msg[:160]}"
        )
    if (
        "curl: (97)" in low
        or "invalid version in initial socks5" in low
        or "forbidden ip" in low
        or ("not supported" in low and "ip" in low)
    ):
        m_ip = re.search(r"forbidden\s+ip\s*=\s*([0-9.]+)", text, re.I)
        ip = m_ip.group(1) if m_ip else "当前公网IP"
        return (
            f"代理商拒绝了你的公网 IP {ip}（握手 403/非 SOCKS，常见为 curl 97 或 CONNECT 403）。"
            "开 TUN 能通是因为出口 IP 变了，不是程序没走你填的代理。"
            f"处理：1) cliproxy 后台把 {ip} 加白名单后关 TUN 再测；"
            "2) 或继续用 TUN（可清空代理框）。程序无法绕过代理商 IP 限制。"
        )
    if "connect aborted" in low or "proxy connect aborted" in low or "curl: (56)" in low:

        return (
            "代理 HTTPS 隧道被中断（CONNECT aborted / curl 56）。"
            "常见原因：当前公网 IP 未在 cliproxy 白名单、账号/地区参数无效、或代理节点不可用。"
            "处理：1) 先点「测试代理」；2) 不行则清空代理并开 TUN；"
            "3) 或换可用节点/把本机 IP 加入白名单。不要 TUN+自定义代理叠用。"
            f" 原始：{msg[:140]}"
        )
    if "407" in low or "proxy authentication" in low:
        return "代理认证失败（407），请检查用户名/密码。"
    if (
        "timed out" in low
        or "timeout" in low
        or "curl: (28)" in low
        or "connection timed out" in low
    ):
        return (
            "经代理访问超时（curl 28）。"
            "本地 Headless 指纹可能仍能生成（不一定要出网），但 Phase0 拉 PayPal 必须代理真通。"
            "处理：1) 点「测试代理」确认出口 IP；2) 失败则清空代理框并开 TUN；"
            "3) 或白名单后重试；4) 避免 TUN 与自定义代理同时开启。"
            f" 原始：{msg[:140]}"
        )
    if "could not resolve" in low or "getaddrinfo" in low:
        return f"代理域名无法解析：{msg}"
    if "failed to perform" in low and ("proxy" in low or "curl:" in low):
        return (
            f"代理链路不可用：{msg[:180]}。"
            "请先测试代理；不可用时清空代理并用 TUN，或修复 cliproxy 白名单/节点。"
        )
    return text if text else str(msg)


def test_proxy_connectivity(proxy_raw: str, proxy_mode: str = "custom") -> dict[str, Any]:
    """Probe outbound proxy. Prefer HTTP probe first to surface provider 403 bodies.

    proxy_mode=system: do not use application HTTP proxy (for OS TUN / system route).
    """
    mode = (proxy_mode or "custom").strip().lower() or "custom"
    raw = (proxy_raw or "").strip()
    if mode == "system":
        # Direct path — if user has TUN, OS routes this; we do not inject cliproxy URL.
        import time as _time
        try:
            import curl_cffi.requests as curl_requests
        except Exception as exc:
            raise ValueError(f"代理测试依赖不可用: {exc}") from exc
        started = _time.time()
        try:
            with curl_requests.Session(timeout=15, impersonate="chrome131") as client:
                # no proxies: follow OS routing (TUN)
                resp = client.get("https://api.ipify.org?format=json")
                status = int(getattr(resp, "status_code", 0) or 0)
                if status != 200:
                    raise ValueError(f"系统出口探测失败 HTTP {status}")
                try:
                    exit_ip = str((resp.json() or {}).get("ip") or "").strip()
                except Exception:
                    exit_ip = (resp.text or "").strip()[:64]
        except Exception as exc:
            raise ValueError(
                f"系统/TUN 出口不可用：{exc}。请确认已开启 TUN/系统代理，且本程序无需再填 cliproxy 账号。"
            ) from exc
        return {
            "ok": True,
            "mode": "system",
            "proxy_label": "系统/TUN",
            "status": 200,
            "exit_ip": exit_ip,
            "latency_ms": int((_time.time() - started) * 1000),
        }
    # Empty raw → try system proxy (Brazil-like). Filled raw → filled first, system fallback.
    saved_env = scrub_process_proxy_env()
    try:
        working, exit_ip, latency_ms, note = resolve_outbound_proxy(
            raw,
            allow_system_fallback=True,
            timeout=15.0,
        )
    finally:
        restore_process_proxy_env(saved_env)

    proxy_config = ProxyConfig(
        enabled=True,
        entry=working,
        resolved_from=note,
    )

    import time as _time
    try:
        import curl_cffi.requests as curl_requests
    except Exception as exc:
        raise ValueError(f"代理测试依赖不可用: {exc}") from exc
    started = _time.time()
    status = 200
    try:
        with curl_requests.Session(timeout=20, impersonate="chrome131") as client:
            if hasattr(client, "trust_env"):
                client.trust_env = False
            client.proxies = {"http": proxy_config.url, "https": proxy_config.url}
            resp = client.get("https://www.paypal.com/robots.txt", allow_redirects=True)
            status = int(getattr(resp, "status_code", 0) or 0)
            if status < 200 or status >= 500:
                raise ValueError(f"PayPal 探测失败 HTTP {status}")
    except Exception as exc:
        raise ValueError(classify_proxy_transport_error(str(exc))) from exc

    return {
        "ok": True,
        "mode": "custom" if raw else "system",
        "proxy_label": proxy_config.label,
        "resolved_scheme": working.scheme,
        "resolve_note": note,
        "status": status,
        "exit_ip": exit_ip,
        "latency_ms": latency_ms or int((_time.time() - started) * 1000),
        "message": (
            f"出口 IP {exit_ip}；路由: {note}"
            if exit_ip
            else f"连通；路由: {note}"
        ),
    }


@dataclass
class WebJob:
    id: str
    owner_device_id: str
    ba_token: str
    phone: str
    country: str = "TH"
    runtime_mode: str = "headless"
    profile: str = "real"
    fingerprint_source: str = "headless"
    datadome_mode: str = "headless"
    mtr_runtime: str = "headless"
    risk_signals_mode: str = "headless"
    buyer_identity_mode: str = "legacy"
    continue_merchant: bool = False
    smsbower_enabled: bool = False
    _smsbower_api_key: str = ""
    debug: bool = False
    max_card_attempts: int = 5
    max_flow_attempts: int = 1
    max_authorize_attempts: int = 3
    card_retry_delay_seconds: float = 6.0
    card_retry_jitter_seconds: float = 2.0
    _roxy_api_key: str = ""
    roxy_api_host: str = "127.0.0.1"
    roxy_api_port: int = 50000
    roxy_headless: bool = True
    roxy_workspace_id: str = ""
    roxy_project_id: str = ""
    proxy_enabled: bool = False
    proxy_mode: str = "custom"
    proxy_label: str = "代理关闭"
    created_at: float = field(default_factory=now_ts)
    updated_at: float = field(default_factory=now_ts)
    started_at: float | None = None
    finished_at: float | None = None
    status: str = "queued"  # queued | running | awaiting_otp | completed | failed
    stage: str = "排队中"
    result: dict[str, Any] | None = None
    error: str = ""
    traceback_text: str = ""
    generated: dict[str, Any] | None = None
    awaiting_prompt: str = ""
    logs: list[dict[str, Any]] = field(default_factory=list)
    _condition: threading.Condition = field(default_factory=threading.Condition, repr=False)
    _input_queue: list[str] = field(default_factory=list, repr=False)
    _proxy_config: ProxyConfig | None = field(default=None, repr=False)

    def set_status(self, status: str, stage: str | None = None) -> None:
        with self._condition:
            self.status = status
            if stage is not None:
                self.stage = stage
            self.updated_at = now_ts()
            self._condition.notify_all()

    def set_generated(self, generated: dict[str, Any]) -> None:
        with self._condition:
            self.generated = generated
            self.updated_at = now_ts()
            self._condition.notify_all()

    def add_log(self, level: str, message: str, ts: float | None = None) -> None:
        with self._condition:
            self.logs.append({
                "time": ts or now_ts(),
                "level": level,
                "message": redact_text(message).rstrip(),
            })
            if len(self.logs) > MAX_LOG_LINES:
                del self.logs[: len(self.logs) - MAX_LOG_LINES]
            self.updated_at = now_ts()
            self._condition.notify_all()

    def wait_for_input(self, prompt: str) -> str:
        with self._condition:
            self.status = "awaiting_otp"
            self.stage = "等待短信验证码 / 新手机号"
            self.awaiting_prompt = redact_text(prompt)
            self.updated_at = now_ts()
            self._condition.notify_all()
            deadline = now_ts() + OTP_INPUT_TIMEOUT_SECONDS
            while not self._input_queue:
                remaining = deadline - now_ts()
                if remaining <= 0:
                    raise TimeoutError("等待验证码/手机号输入超时")
                self._condition.wait(timeout=min(0.5, remaining))
            value = self._input_queue.pop(0).strip()
            self.status = "running"
            self.stage = "已收到输入，继续执行"
            self.awaiting_prompt = ""
            self.updated_at = now_ts()
            self._condition.notify_all()
            return value

    def submit_input(self, value: str) -> None:
        value = (value or "").strip()
        if not value:
            raise ValueError("输入不能为空")
        with self._condition:
            self._input_queue.append(value)
            self.stage = "已提交验证码/手机号，等待程序处理"
            self.updated_at = now_ts()
            self._condition.notify_all()

    def complete(self, result: dict[str, Any]) -> None:
        with self._condition:
            succeeded = isinstance(result, dict) and result.get("status") == "success"
            self.status = "completed" if succeeded else "failed"
            self.stage = "已完成" if succeeded else "执行失败"
            if isinstance(result, dict) and not succeeded:
                raw_err = str(result.get("error") or "流程返回错误状态")
                fixed = classify_proxy_transport_error(raw_err)
                if fixed and fixed != raw_err:
                    result = dict(result)
                    result["error"] = fixed
                self.error = redact_text(fixed or raw_err)
            elif not succeeded:
                self.error = redact_text("流程返回无效结果")
            else:
                self.error = ""
            self.result = result
            self.finished_at = now_ts()
            self.updated_at = now_ts()
            self.awaiting_prompt = ""
            self._condition.notify_all()

    def fail(self, exc: BaseException) -> None:
        with self._condition:
            self.status = "failed"
            self.stage = "执行失败"
            err_text = str(exc)
            low = err_text.lower()
            if any(
                token in low
                for token in (
                    "curl:",
                    "proxy",
                    "timed out",
                    "timeout",
                    "connect aborted",
                    "failed to perform",
                    "代理",
                )
            ):
                err_text = classify_proxy_transport_error(err_text)
            self.error = redact_text(err_text)
            self.traceback_text = redact_text(traceback.format_exc()) if (self.debug and ALLOW_DEBUG_LOGS) else ""
            self.finished_at = now_ts()
            self.updated_at = now_ts()
            self.awaiting_prompt = ""
            self._condition.notify_all()

    def to_dict(self, *, include_logs: bool = True, log_offset: int = 0) -> dict[str, Any]:
        with self._condition:
            logs = self.logs[max(0, log_offset) :] if include_logs else []
            return {
                "id": self.id,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "duration": (self.finished_at or now_ts()) - (self.started_at or self.created_at),
                "status": self.status,
                "stage": self.stage,
                "ba_token": mask_middle(self.ba_token),
                "phone": mask_phone(self.phone),
                "country": self.country,
                "runtime_mode": self.runtime_mode,
            "profile": getattr(self, "profile", "real"),
            "max_flow_attempts": getattr(self, "max_flow_attempts", 1),
                "max_authorize_attempts": getattr(self, "max_authorize_attempts", 3),
                "card_retry_delay_seconds": getattr(self, "card_retry_delay_seconds", 6.0),
                "card_retry_jitter_seconds": getattr(self, "card_retry_jitter_seconds", 2.0),
                "roxy_configured": bool(getattr(self, "_roxy_api_key", "") or os.getenv("PAYPAL_ROXY_API_KEY") or os.getenv("ROXY_API_KEY")),
                "roxy_api_host": getattr(self, "roxy_api_host", "127.0.0.1"),
                "roxy_api_port": getattr(self, "roxy_api_port", 50000),
                "roxy_headless": bool(getattr(self, "roxy_headless", True)),
                "fingerprint_source": getattr(self, "fingerprint_source", "auto"),
            "datadome_mode": getattr(self, "datadome_mode", "auto"),
            "mtr_runtime": getattr(self, "mtr_runtime", "auto"),
            "risk_signals_mode": getattr(self, "risk_signals_mode", "auto"),
            "buyer_identity_mode": getattr(self, "buyer_identity_mode", "legacy"),
            "continue_merchant": bool(getattr(self, "continue_merchant", False)),
                "smsbower_enabled": self.smsbower_enabled,
                "debug": self.debug and ALLOW_DEBUG_LOGS,
                "max_card_attempts": self.max_card_attempts,
                "proxy_enabled": self.proxy_enabled,
                "proxy_mode": getattr(self, "proxy_mode", "custom"),
                "proxy_label": self.proxy_label,
                "generated": sanitize_payload(self.generated),
                "awaiting_otp": self.status == "awaiting_otp",
                "awaiting_prompt": redact_text(self.awaiting_prompt),
                "result": safe_result_payload(self.result),
                "error": redact_text(self.error),
                "traceback": self.traceback_text if (self.debug and ALLOW_DEBUG_LOGS) else "",
                "logs": logs,
                "log_count": len(self.logs),
            }


JOBS: dict[str, WebJob] = {}
JOBS_LOCK = threading.RLock()


def client_rate_limit(bucket: str, key: str, *, limit: int, window_seconds: int) -> bool:
    current_ts = now_ts()
    with RATE_LOCK:
        cutoff = current_ts - window_seconds
        values = [ts for ts in RATE_BUCKETS.get((bucket, key), []) if ts >= cutoff]
        if len(values) >= limit:
            RATE_BUCKETS[(bucket, key)] = values
            return False
        values.append(current_ts)
        RATE_BUCKETS[(bucket, key)] = values
        return True


def prune_jobs_locked() -> None:
    """Drop old finished jobs and keep the in-memory job list bounded."""
    current_ts = now_ts()
    for job_id, job in list(JOBS.items()):
        if job.status in ACTIVE_STATUSES:
            continue
        finished_or_updated = job.finished_at or job.updated_at
        if current_ts - finished_or_updated > JOB_RETENTION_SECONDS:
            JOBS.pop(job_id, None)

    if len(JOBS) <= MAX_TOTAL_JOBS:
        return

    removable = sorted(
        [job for job in JOBS.values() if job.status not in ACTIVE_STATUSES],
        key=lambda item: item.updated_at,
    )
    while len(JOBS) > MAX_TOTAL_JOBS and removable:
        JOBS.pop(removable.pop(0).id, None)


def active_job_count(owner_device_id: str | None = None) -> int:
    with JOBS_LOCK:
        return sum(
            1
            for job in JOBS.values()
            if job.status in ACTIVE_STATUSES and (owner_device_id is None or job.owner_device_id == owner_device_id)
        )


# ----------------------------- PayPal flow adapter -----------------------------


class WebPayPalFlow(PayPalFlow):
    """PayPalFlow adapter that asks the web page for OTP/new-phone input."""

    def __init__(self, *args: Any, job: WebJob, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.job = job

    def _set_stage(self, stage: str) -> None:
        self.job.set_status("running", stage)

    def _phase0_initial_load(self):
        self._set_stage("Phase 0：加载协议页")
        return super()._phase0_initial_load()

    def _phase1_risk_controls(self):
        self._set_stage("Phase 1 risk / fingerprint")
        parent = getattr(PayPalFlow, "_phase1_risk_controls", None)
        if callable(parent):
            return parent(self)
        return None

    def _phase2_create_account(self):
        self._set_stage("Phase 2：进入创建账户流程")
        return super()._phase2_create_account()

    def _phase3_signup_and_2fa(self):
        self._set_stage("Phase 3：短信验证与注册")
        return super()._phase3_signup_and_2fa()

    def _elevate_guest_identity(self):
        self._set_stage("Buyer：提升 Guest 身份")
        return super()._elevate_guest_identity()

    def _bind_buyer_to_current_ec(self):
        self._set_stage("Buyer：绑定当前 EC")
        return super()._bind_buyer_to_current_ec()

    def _phase4_authorize(self, *args, **kwargs):
        self._set_stage("Phase 4：提交授权")
        return super()._phase4_authorize(*args, **kwargs)



    def _on_full_retry_generated(self, flow_attempt: int):
        self.job.set_status(
            "running",
            f"整流程重试 {flow_attempt}/{self.max_flow_attempts}，已重新生成资料",
        )
        self.job.set_generated(public_generated_payload(self.user, self.card, self.address))

    def _on_signup_retry_generated(self, signup_attempt: int, reason: str):
        self.job.set_status(
            "running",
            f"注册换卡重试 {signup_attempt}/{self.max_card_attempts}，已更新账号/卡信息",
        )
        self.job.set_generated(public_generated_payload(self.user, self.card, self.address))

    def _prompt_operator(self, prompt: str) -> str:
        logger.info(prompt)
        return self.job.wait_for_input(prompt)

    def _confirm_phone_with_retry(self, token: str, signup_url: str):
        """Web version of the CLI input loop."""
        while True:
            try:
                auth_id, challenge_id = self._initiate_2fa_phone_confirmation(token, signup_url)
            except Exception as e:
                logger.error("Failed to initiate OTP for {}: {}", self._masked_phone(), e)
                while True:
                    value = self._prompt_operator(
                        f"发送验证码失败。请输入【新的】手机号重新发送（{phone_input_hint(self.job.country, getattr(self.user, "phone", ""))}）；输入 q 退出。"
                    )
                    if value.lower() in {"q", "quit", "exit"}:
                        raise RuntimeError("OTP confirmation cancelled by user") from e
                    try:
                        previous = str(getattr(self.user, "phone", "") or "")
                        self._update_user_phone(value)
                        if previous and str(getattr(self.user, "phone", "") or "") == previous:
                            logger.warning(
                                "你提交的手机号与刚才相同（{}）；仍会重试发送，建议换一个同国可用号码。",
                                self._masked_phone(),
                            )
                        break
                    except ValueError as phone_error:
                        logger.warning("手机号无效：{}。请重新输入。", phone_error)
                continue

            logger.info("SMS verification code sent to phone: {}", self._masked_phone())

            # SMSBower auto OTP full path (optional) — fall back to manual input
            provider = getattr(self, "sms_provider", None) or getattr(self, "_otp_provider", None)
            if provider is not None:
                try:
                    from paypal.runtime_bridge import reserve_smsbower_number
                    self.job.set_status("running", "SMSBower 自动接码中…")
                    activation = getattr(self, "_smsbower_activation", None)
                    # If user phone may not be SMSBower-owned, reserve number then re-initiate OTP once
                    if activation is None and hasattr(provider, "reserve_number"):
                        reserved = reserve_smsbower_number(self)
                        if reserved.get("ok"):
                            activation = getattr(self, "_smsbower_activation", None)
                            logger.info("SMSBower number ready, re-initiating OTP to {}", self._masked_phone())
                            try:
                                if hasattr(provider, "mark_sms_sent") and activation is not None:
                                    # will mark after re-init
                                    pass
                                auth_id, challenge_id = self._initiate_2fa_phone_confirmation(token, signup_url)
                                if activation is not None and hasattr(provider, "mark_sms_sent"):
                                    provider.mark_sms_sent(activation)
                            except Exception as re_exc:
                                logger.warning("Re-initiate OTP after SMSBower reserve failed: {}", re_exc)
                    if activation is not None and hasattr(provider, "wait_for_code"):
                        if hasattr(provider, "mark_sms_sent"):
                            try:
                                provider.mark_sms_sent(activation)
                            except Exception:
                                pass
                        code = provider.wait_for_code(activation)
                        if code:
                            code = "".join(ch for ch in str(code) if ch.isdigit())
                        if code and 4 <= len(code) <= 8:
                            logger.info("SMSBower code received (len={}), confirming…", len(code))
                            if self._confirm_2fa_phone_confirmation(
                                token, signup_url, auth_id, challenge_id, code
                            ):
                                return
                            logger.warning("SMSBower code rejected by PayPal; fall back to manual OTP")
                        else:
                            logger.warning("SMSBower did not return code in time; fall back to manual OTP")
                except Exception as sms_exc:
                    logger.warning("SMSBower auto OTP failed, fall back to manual: {}", sms_exc)

            while True:
                value = self._prompt_operator(
                    f"请输入6位短信验证码；如需换号，输入【新的】手机号（{phone_input_hint(self.job.country, getattr(self.user, "phone", ""))}）；输入 q 退出。"
                )

                if value.lower() in {"q", "quit", "exit"}:
                    raise RuntimeError("OTP confirmation cancelled by user")

                if len(value) == 6 and value.isdigit():
                    if self._confirm_2fa_phone_confirmation(
                        token,
                        signup_url,
                        auth_id,
                        challenge_id,
                        value,
                    ):
                        return
                    logger.warning("验证码验证失败。可以继续输入新的6位验证码，或输入新手机号重新发送验证码。")
                    continue

                try:
                    self._update_user_phone(value)
                    logger.info("Re-sending OTP to the new phone...")
                    break
                except ValueError as e:
                    logger.warning("输入既不是6位验证码，也不是有效手机号：{}。请重新输入。", e)


# ----------------------------- logging -----------------------------


def _job_log_sink(message: Any) -> None:
    record = message.record
    job_id = record["extra"].get("job_id")
    if not job_id:
        return
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return
    level = record["level"].name
    if level == "DEBUG" and not job.debug:
        return
    job.add_log(level, record["message"], record["time"].timestamp())


def _console_log_sink(message: Any) -> None:
    record = message.record
    level = record["level"].name
    ts = record["time"].strftime("%H:%M:%S")
    text = redact_text(record["message"])
    sys.stderr.write(f"{ts} | {level:<8} | {text}\n")


def configure_logging() -> None:
    logger.remove()
    logger.add(_console_log_sink, level="INFO")
    logger.add(_job_log_sink, level="DEBUG", filter=lambda r: bool(r["extra"].get("job_id")))


# ----------------------------- runner -----------------------------


def create_job(
    owner_device_id: str,
    ba_token: str,
    phone: str,
    debug: bool,
    max_card_attempts: int,
    max_flow_attempts: int = 1,
    max_authorize_attempts: int = 3,
    card_retry_delay_seconds: float = 6.0,
    card_retry_jitter_seconds: float = 2.0,
    roxy_api_key: str = "",
    roxy_api_host: str = "127.0.0.1",
    roxy_api_port: int = 50000,
    roxy_headless: bool = True,
    roxy_workspace_id: str = "",
    roxy_project_id: str = "",
    proxy_enabled: bool = False,
    proxy: str = "",
    country: str = "TH",
    runtime_mode: str = "",
    profile: str = "real",
    fingerprint_source: str = "headless",
    datadome_mode: str = "headless",
    mtr_runtime: str = "headless",
    risk_signals_mode: str = "",
    continue_merchant: bool = False,
    buyer_identity_mode: str = "legacy",
    smsbower_enabled: bool = False,
    smsbower_api_key: str = "",
) -> WebJob:
    ba_token = (ba_token or "").strip()
    if not ba_token:
        raise ValueError("BA Token 不能为空")
    if not BA_TOKEN_RE.fullmatch(ba_token):
        raise ValueError("BA Token 格式不正确")
    if not (phone or "").strip():
        raise ValueError("手机号不能为空")
    country = normalize_region(country)
    phone = normalize_region_phone(country, phone)
    profile = "real"  # Web UI is real-run only (no test/smoke profile)
    continue_merchant = False  # A-layer only (aligned with openai-paypal; no B/C switch)

    # Brazil-style fine knobs (defaults headless; protocol allowed on DataDome)
    fingerprint_source = str(fingerprint_source or "headless").strip().lower().replace("-", "_")
    datadome_mode = str(datadome_mode or "headless").strip().lower().replace("-", "_")
    mtr_runtime = str(mtr_runtime or "headless").strip().lower().replace("-", "_")
    if fingerprint_source not in FINGERPRINT_SOURCE_CHOICES:
        raise ValueError(f"unsupported fingerprint_source: {fingerprint_source}")
    if datadome_mode not in DATADOME_MODE_CHOICES:
        raise ValueError(f"unsupported datadome_mode: {datadome_mode}")
    if mtr_runtime not in MTR_RUNTIME_CHOICES:
        raise ValueError(f"unsupported mtr_runtime: {mtr_runtime}")

    buyer_identity_mode = str(buyer_identity_mode or "legacy").strip().lower().replace("-", "_").replace(" ", "_")
    if buyer_identity_mode in {"", "original", "default", "classic", "v1", "phase4"}:
        buyer_identity_mode = "legacy"
    elif buyer_identity_mode in {
        "guest_elevate", "bind_ec", "elevate", "guest_bind", "bind", "v2", "elevate_guest_bind_ec",
    }:
        buyer_identity_mode = "elevate_bind"
    elif buyer_identity_mode not in {"legacy", "elevate_bind"}:
        raise ValueError(f"unsupported buyer_identity_mode: {buyer_identity_mode}")

    roxy_api_key = (roxy_api_key or "").strip()
    roxy_api_host = (roxy_api_host or "127.0.0.1").strip() or "127.0.0.1"
    try:
        roxy_api_port = int(roxy_api_port or 50000)
    except Exception:
        roxy_api_port = 50000
    roxy_api_port = max(1, min(roxy_api_port, 65535))
    roxy_workspace_id = (roxy_workspace_id or "").strip()
    roxy_project_id = (roxy_project_id or "").strip()
    if roxy_modes_need_key(fingerprint_source, datadome_mode, mtr_runtime):
        env_key = (os.getenv("PAYPAL_ROXY_API_KEY") or os.getenv("ROXY_API_KEY") or "").strip()
        if not roxy_api_key and not env_key:
            raise ValueError("已选择 Roxy/自动，请在前端填写 Roxy API Key，或配置环境变量 PAYPAL_ROXY_API_KEY")
        apply_web_roxy_config(
            roxy_api_key=roxy_api_key or env_key,
            roxy_api_host=roxy_api_host,
            roxy_api_port=roxy_api_port,
            roxy_headless=bool(roxy_headless),
            roxy_workspace_id=roxy_workspace_id,
            roxy_project_id=roxy_project_id,
        )
    elif roxy_api_key:
        # still allow saving key for later even if not used this job
        apply_web_roxy_config(
            roxy_api_key=roxy_api_key,
            roxy_api_host=roxy_api_host,
            roxy_api_port=roxy_api_port,
            roxy_headless=bool(roxy_headless),
            roxy_workspace_id=roxy_workspace_id,
            roxy_project_id=roxy_project_id,
        )

    risk_signals_mode = implicit_risk_signals_mode(
        fingerprint_source,
        datadome_mode,
        mtr_runtime,
        risk_signals_mode,
    )
    if risk_signals_mode not in RISK_SIGNALS_MODE_CHOICES:
        risk_signals_mode = "headless"

    # Coarse mode for browser engine; fine knobs are source of truth (Brazil Web).
    # Only honor explicit runtime_mode if the client actually sent one.
    explicit_runtime = str(runtime_mode or "").strip().lower().replace("-", "_")
    if explicit_runtime in {"", "default"}:
        runtime_mode = derive_runtime_mode(fingerprint_source, datadome_mode, mtr_runtime)
    else:
        runtime_mode = explicit_runtime

    resolved = resolve_and_apply(
        runtime_mode=runtime_mode,
        profile=profile,
        fingerprint_source=fingerprint_source,
        datadome_mode=datadome_mode,
        mtr_runtime=mtr_runtime,
        risk_signals_mode=risk_signals_mode,
        continue_merchant=False,
    )
    # Prefer explicit fine modes (Brazil path); coarse comes from resolver/engine.
    runtime_mode = resolved.runtime_mode or runtime_mode
    profile = "real"
    # fine knobs already validated above — keep them authoritative
    fingerprint_source = fingerprint_source
    datadome_mode = datadome_mode
    mtr_runtime = mtr_runtime
    risk_signals_mode = risk_signals_mode or resolved.risk_signals_mode
    continue_merchant = False  # never run B/C from Web (A-layer only)
    smsbower_enabled = bool(smsbower_enabled)
    smsbower_api_key = (smsbower_api_key or "").strip()
    try:
        max_card_attempts = int(max_card_attempts)
    except Exception as exc:
        raise ValueError("最大换卡次数必须是数字") from exc
    max_card_attempts = max(1, min(max_card_attempts, 20))
    try:
        max_flow_attempts = int(max_flow_attempts)
    except Exception:
        max_flow_attempts = 1
    max_flow_attempts = max(1, min(max_flow_attempts, 5))
    try:
        max_authorize_attempts = int(max_authorize_attempts)
    except Exception:
        max_authorize_attempts = 3
    max_authorize_attempts = max(1, min(max_authorize_attempts, 10))
    try:
        card_retry_delay_seconds = float(card_retry_delay_seconds)
    except Exception:
        card_retry_delay_seconds = 6.0
    card_retry_delay_seconds = max(0.0, min(card_retry_delay_seconds, 60.0))
    try:
        card_retry_jitter_seconds = float(card_retry_jitter_seconds)
    except Exception:
        card_retry_jitter_seconds = 2.0
    card_retry_jitter_seconds = max(0.0, min(card_retry_jitter_seconds, 30.0))
    debug = bool(debug) and ALLOW_DEBUG_LOGS
    proxy_raw = (proxy or "").strip()
    if proxy_raw:
        # 前端填写的代理优先；解析失败直接报错给用户
        proxy_config = build_proxy_config(enabled=True, raw=proxy_raw)
    elif proxy_enabled:
        # 兼容旧开关：未填串时回退到服务端配置池
        proxy_config = build_proxy_config(enabled=True)
    else:
        proxy_config = build_proxy_config(enabled=False)

    job = WebJob(
        id=uuid.uuid4().hex[:12],
        owner_device_id=owner_device_id,
        ba_token=ba_token,
        phone=phone,
        country=country,
        runtime_mode=runtime_mode,
        profile=profile,
        fingerprint_source=fingerprint_source,
        datadome_mode=datadome_mode,
        mtr_runtime=mtr_runtime,
        risk_signals_mode=risk_signals_mode,
        buyer_identity_mode=buyer_identity_mode,
        continue_merchant=continue_merchant,
        smsbower_enabled=smsbower_enabled,
        _smsbower_api_key=smsbower_api_key,
        debug=debug,
        max_card_attempts=max_card_attempts,
        max_flow_attempts=max_flow_attempts,
        max_authorize_attempts=max_authorize_attempts,
        card_retry_delay_seconds=card_retry_delay_seconds,
        card_retry_jitter_seconds=card_retry_jitter_seconds,
        _roxy_api_key=roxy_api_key,
        roxy_api_host=roxy_api_host,
        roxy_api_port=roxy_api_port,
        roxy_headless=bool(roxy_headless),
        roxy_workspace_id=roxy_workspace_id,
        roxy_project_id=roxy_project_id,
        proxy_enabled=proxy_config.enabled,
        proxy_mode="custom",
        proxy_label=proxy_config.label,
        _proxy_config=proxy_config,
    )
    with JOBS_LOCK:
        prune_jobs_locked()
        total_active = sum(1 for item in JOBS.values() if item.status in ACTIVE_STATUSES)
        user_active = sum(
            1
            for item in JOBS.values()
            if item.status in ACTIVE_STATUSES and item.owner_device_id == owner_device_id
        )
        if total_active >= MAX_TOTAL_JOBS:
            raise ValueError("当前任务队列已满，请稍后再试")
        if user_active >= MAX_ACTIVE_JOBS_PER_DEVICE:
            raise ValueError(f"当前浏览器已有 {user_active} 个未完成任务，请等待完成后再启动")
        if len(JOBS) >= MAX_TOTAL_JOBS:
            raise ValueError("历史任务数量已达上限，请稍后再试")
        JOBS[job.id] = job
    thread = threading.Thread(target=run_job, args=(job,), name=f"paypal-web-{job.id}", daemon=True)
    thread.start()
    return job


def run_job(job: WebJob) -> None:
    with logger.contextualize(job_id=job.id):
        acquired = False
        try:
            if not RUNNER_SEMAPHORE.acquire(blocking=False):
                job.set_status("queued", "等待可用执行槽")
                logger.info("Job queued, waiting for execution slot")
                RUNNER_SEMAPHORE.acquire()
            acquired = True
            saved_proxy_env: dict[str, str] = {}
            job.started_at = now_ts()
            # per-job Roxy settings from Web form
            apply_web_roxy_config(
                roxy_api_key=getattr(job, "_roxy_api_key", "") or "",
                roxy_api_host=getattr(job, "roxy_api_host", "127.0.0.1"),
                roxy_api_port=getattr(job, "roxy_api_port", 50000),
                roxy_headless=getattr(job, "roxy_headless", True),
                roxy_workspace_id=getattr(job, "roxy_workspace_id", ""),
                roxy_project_id=getattr(job, "roxy_project_id", ""),
            )
            job.set_status("running", "生成用户、卡片和地址")
            proxy_config = job._proxy_config or build_proxy_config(enabled=job.proxy_enabled)
            saved_proxy_env = scrub_process_proxy_env()
            try:
                filled_raw = ""
                if proxy_config.enabled and proxy_config.entry:
                    filled_raw = proxy_config.entry.url or ""
                # Brazil-like: filled residential first; if provider bans China IP,
                # automatically use Windows 系统代理 (e.g. 127.0.0.1:7897).
                working, exit_ip, latency_ms, note = resolve_outbound_proxy(
                    filled_raw,
                    allow_system_fallback=True,
                    timeout=15.0,
                )
                original_scheme = (
                    proxy_config.entry.scheme if proxy_config.entry else ""
                )
                proxy_config = ProxyConfig(
                    enabled=True,
                    entry=working,
                    resolved_from=note,
                )
                job._proxy_config = proxy_config
                logger.info(
                    "Proxy resolved for job: {} exit_ip={} latency={}ms note={} filled_scheme={}",
                    proxy_config.label,
                    exit_ip or "",
                    latency_ms,
                    note,
                    original_scheme,
                )
                if "system-fallback" in note or note.startswith("system"):
                    logger.warning(
                        "Using system/local proxy path ({}). "
                        "Filled cliproxy was skipped or blocked for this network.",
                        note,
                    )
            except Exception:
                restore_process_proxy_env(saved_proxy_env)
                raise
            job.proxy_enabled = proxy_config.enabled
            job.proxy_label = proxy_config.label
            user = generate_user(job.phone, country=job.country)
            card = generate_card()
            address = generate_address(country=job.country)
            job.set_generated(public_generated_payload(user, card, address))

            logger.info("Web job started: {}", job.id)
            logger.info("Proxy: {}", proxy_config.label)
            # Proxy already resolved above (explicit filled endpoint only).
            logger.info("Runtime mode: {}", getattr(job, "runtime_mode", "protocol"))
            logger.info("SMSBower: {}", "on" if getattr(job, "smsbower_enabled", False) else "off")
            logger.info("User: {} {}", user.first_name, user.last_name)
            logger.info("Email: {}", mask_email(user.email))
            logger.info("Phone: {}", mask_phone(user.phone))
            logger.info(
                "Address generated: {}, {}-{}",
                address.district,
                address.city,
                address.state,
            )

            logger.info(
                "Runtime modes: fingerprint={} datadome={} mtr={} buyer={}",
                getattr(job, "fingerprint_source", ""),
                getattr(job, "datadome_mode", ""),
                getattr(job, "mtr_runtime", ""),
                getattr(job, "buyer_identity_mode", "legacy"),
            )

            flow = WebPayPalFlow(
                ba_token=job.ba_token,
                user=user,
                card=card,
                address=address,
                max_card_attempts=job.max_card_attempts,
                max_flow_attempts=getattr(job, "max_flow_attempts", 1),
                max_authorize_attempts=getattr(job, "max_authorize_attempts", 3),
                card_retry_delay_seconds=getattr(job, "card_retry_delay_seconds", 6.0),
                card_retry_jitter_seconds=getattr(job, "card_retry_jitter_seconds", 2.0),
                proxy_config=proxy_config,
                runtime_mode=getattr(job, "runtime_mode", "headless"),
                profile=getattr(job, "profile", "real"),
                fingerprint_source=getattr(job, "fingerprint_source", "headless"),
                datadome_mode=getattr(job, "datadome_mode", "headless"),
                mtr_runtime=getattr(job, "mtr_runtime", "headless"),
                risk_signals_mode=getattr(job, "risk_signals_mode", "headless"),
                buyer_identity_mode=getattr(job, "buyer_identity_mode", "legacy"),
                continue_merchant=False,
                smsbower_enabled=getattr(job, "smsbower_enabled", False),
                smsbower_api_key=getattr(job, "_smsbower_api_key", ""),
                job=job,
            )
            result = flow.run()
            if isinstance(result, dict):
                result.setdefault("region", job.country)
                job_dir = ROOT / "runtime" / "jobs" / job.id
                job_dir.mkdir(parents=True, exist_ok=True)
                if "b_layer" not in result:
                    result["b_layer"] = build_b_layer_evidence(result)
                try:
                    # Write the A-layer handoff first; the merchant runner replaces
                    # the sidecar with the final B/C evidence after its HTTP hops.
                    persist_b_layer_evidence(job_dir, result)
                    result["b_layer_evidence_path"] = str(job_dir / "b_layer_evidence.json")
                except Exception as persist_exc:
                    logger.warning("b_layer persist failed: {}", persist_exc)
                cont = bool(getattr(job, "continue_merchant", False))
                result["runtime"] = {
                    "profile": getattr(job, "profile", "real"),
                    "runtime_mode": getattr(job, "runtime_mode", "auto"),
                    "fingerprint_source": getattr(job, "fingerprint_source", "auto"),
                    "datadome_mode": getattr(job, "datadome_mode", "auto"),
                    "mtr_runtime": getattr(job, "mtr_runtime", "auto"),
                    "risk_signals_mode": getattr(job, "risk_signals_mode", "auto"),
                    "buyer_identity_mode": getattr(job, "buyer_identity_mode", "legacy"),
                    "continue_merchant": cont,
                }
                if cont and str(result.get("status") or "").lower() in {"success", "ok", "completed", "authorized"}:
                    merchant = complete_merchant_chain(
                        result,
                        proxies=[proxy_config.url] if proxy_config.url else None,
                        log=lambda message: job.add_log("INFO", message),
                        session_path=str(job_dir / "merchant_session.json"),
                    )
                    result["session_cookies"] = merchant.get("session_cookies", result.get("session_cookies", []))
                    result["b_layer"] = build_b_layer_evidence({**result, **merchant})
                    annotate_layer_status(result, merchant=merchant, continue_merchant=True)
                else:
                    annotate_layer_status(result, continue_merchant=False)
            job.complete(result)
        except BaseException as exc:  # keep worker alive and expose details in UI
            err_text = str(exc)
            low = err_text.lower()
            if any(
                token in low
                for token in (
                    "curl:",
                    "proxy",
                    "timed out",
                    "timeout",
                    "connect aborted",
                    "failed to perform",
                    "代理",
                )
            ):
                err_text = classify_proxy_transport_error(err_text)
                logger.error("Web job failed: {}", redact_text(err_text))
                job.fail(ValueError(err_text))
            else:
                logger.error("Web job failed: {}", redact_text(exc))
                job.fail(exc)
        finally:
            try:
                restore_process_proxy_env(locals().get("saved_proxy_env") or {})
            except Exception:
                pass
            if acquired:
                RUNNER_SEMAPHORE.release()


# ----------------------------- HTTP server -----------------------------


class WebHandler(BaseHTTPRequestHandler):
    server_version = "PayPalWebUI/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter stdlib server logs
        try:
            text = fmt % args
        except Exception:
            text = fmt
        logger.debug("HTTP {}", redact_text(text))

    def client_key(self) -> str:
        host = self.client_address[0] if self.client_address else "unknown"
        return f"{host}:{self.get_device_id()}"

    def check_rate_limit(self, bucket: str, *, limit: int, window_seconds: int) -> bool:
        key = self.client_key()
        if client_rate_limit(bucket, key, limit=limit, window_seconds=window_seconds):
            return True
        self.send_error_json(HTTPStatus.TOO_MANY_REQUESTS, "请求过于频繁，请稍后再试")
        return False

    def validate_post_request(self) -> bool:
        host = self.headers.get("Host", "")
        for header_name in ("Origin", "Referer"):
            raw = self.headers.get(header_name, "")
            if not raw:
                continue
            parsed = urlparse(raw)
            if parsed.netloc and parsed.netloc != host:
                self.send_error_json(HTTPStatus.FORBIDDEN, "跨站请求被拒绝")
                return False

        try:
            content_length = int(self.headers.get("Content-Length", "0") or 0)
        except Exception:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Content-Length 无效")
            return False
        content_type = self.headers.get("Content-Type", "")
        if content_length > 0 and "application/json" not in content_type.lower():
            self.send_error_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Content-Type 必须是 application/json")
            return False
        return True

    def get_device_id(self) -> str:
        cached = getattr(self, "_device_id", "")
        if cached:
            return cached
        cookies = parse_cookie_header(self.headers.get("Cookie", ""))
        device_id = cookies.get(DEVICE_COOKIE_NAME, "").strip()
        if not DEVICE_ID_RE.fullmatch(device_id):
            device_id = uuid.uuid4().hex
            self._set_device_cookie = device_id
        self._device_id = device_id
        return device_id

    def get_authorized_job(self, job_id: str) -> WebJob | None:
        job = get_job(job_id)
        if not job or job.owner_device_id != self.get_device_id():
            self.send_error_json(HTTPStatus.NOT_FOUND, "任务不存在")
            return None
        return job

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/regions":
            regions = list_regions_public()
            return self.send_json(list_matrix_public(regions))
        if path == "/api/runtime":
            resolved = resolve_runtime()
            return self.send_json({
                "default": {
                    "fingerprint_source": "headless",
                    "datadome_mode": "headless",
                    "mtr_runtime": "headless",
                    "risk_signals_mode": "headless",
                    "runtime_mode": "headless",
                    "profile": "real",
                },
                "resolved": resolved.as_public_dict(),
                "profiles": ["real"],
                "fingerprint_sources": ["headless", "roxy", "random", "auto"],
                "datadome_modes": ["headless", "roxy", "protocol", "auto", "off"],
                "mtr_runtimes": ["headless", "roxy", "python_generated", "auto", "block", "off"],
                "buyer_identity_modes": [
                    {"value": "legacy", "label": "原版流程"},
                    {"value": "elevate_bind", "label": "注册后升 Guest、绑 EC 再授权"},
                ],
                "notes": [
                    "Aligned with openai-paypal Web: three fine knobs, default headless",
                    "Roxy optional when Local API + key available",
                    "auto prefers Roxy then falls back",
                    "retries available like Brazil Web",
                    "Web is real-run only; A-layer only (no merchant B/C)",
                ],
            })
        if path == "/api/health":
            return self.send_json({"ok": True, "time": now_ts()})
        if path == "/api/jobs":
            device_id = self.get_device_id()
            with JOBS_LOCK:
                prune_jobs_locked()
                jobs = sorted(
                    [job for job in JOBS.values() if job.owner_device_id == device_id],
                    key=lambda j: j.created_at,
                    reverse=True,
                )
            return self.send_json({"jobs": [j.to_dict(include_logs=False) for j in jobs]})
        if path.startswith("/api/jobs/"):
            job_id = path.split("/", 3)[3]
            job = self.get_authorized_job(job_id)
            if not job:
                return
            query = self.parse_query(parsed.query)
            try:
                log_offset = int(query.get("log_offset", "0") or 0)
            except Exception:
                log_offset = 0
            return self.send_json(job.to_dict(include_logs=True, log_offset=log_offset))
        if path.startswith("/api/"):
            return self.send_error_json(HTTPStatus.NOT_FOUND, "接口不存在")
        return self.serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if not self.validate_post_request():
            return
        if path == "/api/proxy/test":
            if not self.check_rate_limit("proxy_test", limit=30, window_seconds=600):
                return
            try:
                data = self.read_json()
                result = test_proxy_connectivity(
                    str(data.get("proxy") or data.get("proxy_url") or data.get("proxy_raw") or ""),
                    proxy_mode=str(data.get("proxy_mode") or data.get("mode") or "custom"),
                )
                return self.send_json(result)
            except Exception as exc:
                return self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))


        if path == "/api/roxy/test":
            if not self.check_rate_limit("roxy_test", limit=30, window_seconds=600):
                return
            try:
                data = self.read_json()
                result = test_roxy_connectivity(
                    roxy_api_key=str(data.get("roxy_api_key") or data.get("api_key") or ""),
                    roxy_api_host=str(data.get("roxy_api_host") or data.get("host") or "127.0.0.1"),
                    roxy_api_port=data.get("roxy_api_port") or data.get("port") or 50000,
                    roxy_headless=bool(data.get("roxy_headless", True)),
                    roxy_workspace_id=str(data.get("roxy_workspace_id") or ""),
                    roxy_project_id=str(data.get("roxy_project_id") or ""),
                )
                if not result.get("ok"):
                    return self.send_json(result)
                return self.send_json(result)
            except Exception as exc:
                return self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

        if path == "/api/jobs":
            if not self.check_rate_limit("job_create", limit=20, window_seconds=600):
                return
            try:
                data = self.read_json()
                fingerprint_source = str(data.get("fingerprint_source", "headless") or "headless")
                datadome_mode = str(data.get("datadome_mode", "headless") or "headless")
                mtr_runtime = str(data.get("mtr_runtime", "headless") or "headless")
                job = create_job(
                    owner_device_id=self.get_device_id(),
                    ba_token=data.get("ba_token", ""),
                    phone=data.get("phone", ""),
                    debug=bool(data.get("debug", False)),
                    max_card_attempts=int(data.get("max_card_attempts", 5) or 5),
                    max_flow_attempts=int(data.get("max_flow_attempts", 1) or 1),
                    max_authorize_attempts=int(data.get("max_authorize_attempts", 3) or 3),
                    card_retry_delay_seconds=float(data.get("card_retry_delay_seconds", 6) or 0),
                    card_retry_jitter_seconds=float(data.get("card_retry_jitter_seconds", 2) or 0),
                    roxy_api_key=str(data.get("roxy_api_key", "") or ""),
                    roxy_api_host=str(data.get("roxy_api_host", "127.0.0.1") or "127.0.0.1"),
                    roxy_api_port=int(data.get("roxy_api_port", 50000) or 50000),
                    roxy_headless=bool(data.get("roxy_headless", True)),
                    roxy_workspace_id=str(data.get("roxy_workspace_id", "") or ""),
                    roxy_project_id=str(data.get("roxy_project_id", "") or ""),
                    proxy_enabled=bool(data.get("proxy_enabled", False)),
                    proxy=str(
                        data.get("proxy")
                        or data.get("proxy_url")
                        or data.get("proxy_raw")
                        or ""
                    ),
                    country=str(data.get("country") or data.get("region") or "TH"),
                    runtime_mode=str(data.get("runtime_mode") or data.get("runtime") or ""),
                    fingerprint_source=fingerprint_source,
                    datadome_mode=datadome_mode,
                    mtr_runtime=mtr_runtime,
                    risk_signals_mode=str(data.get("risk_signals_mode") or ""),
                    buyer_identity_mode=str(
                        data.get("buyer_identity_mode")
                        or data.get("identity_mode")
                        or data.get("buyer_mode")
                        or "legacy"
                    ),
                    smsbower_enabled=bool(data.get("smsbower_enabled") or data.get("smsbower") or False),
                    smsbower_api_key=str(data.get("smsbower_api_key") or ""),
                )
                return self.send_json({"job": job.to_dict(include_logs=False)}, status=HTTPStatus.CREATED)
            except Exception as exc:
                return self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

        if path.startswith("/api/jobs/") and path.endswith("/otp"):
            parts = path.split("/")
            job_id = parts[3] if len(parts) > 3 else ""
            job = self.get_authorized_job(job_id)
            if not job:
                return
            try:
                data = self.read_json()
                value = str(data.get("value", "")).strip()
                job.submit_input(value)
                job.add_log("INFO", "已从网页提交验证码/手机号。")
                return self.send_json({"ok": True, "job": job.to_dict(include_logs=False)})
            except Exception as exc:
                return self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

        return self.send_error_json(HTTPStatus.NOT_FOUND, "接口不存在")

    @staticmethod
    def parse_query(query: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for part in query.split("&"):
            if not part:
                continue
            key, _, value = part.partition("=")
            result[unquote(key)] = unquote(value)
        return result

    def read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except Exception as exc:
            raise ValueError("Content-Length 无效") from exc
        if length <= 0:
            return {}
        if length > 1024 * 1024:
            raise ValueError("请求体太大")
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("JSON 必须是对象")
        return data

    def serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            file_path = STATIC_DIR / "index.html"
        elif path.startswith("/static/"):
            rel = path.removeprefix("/static/")
            file_path = STATIC_DIR / rel
        else:
            file_path = STATIC_DIR / "index.html"

        try:
            resolved = file_path.resolve()
            resolved.relative_to(STATIC_DIR.resolve())
        except Exception:
            return self.send_error_json(HTTPStatus.FORBIDDEN, "非法路径")

        if not resolved.exists() or not resolved.is_file():
            return self.send_error_json(HTTPStatus.NOT_FOUND, "文件不存在")

        content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        data = resolved.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store" if resolved.name == "index.html" else "public, max-age=3600")
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(data)

    def send_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'",
        )

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers()
        device_cookie = getattr(self, "_set_device_cookie", "")
        if device_cookie:
            cookie_attrs = [
                f"{DEVICE_COOKIE_NAME}={device_cookie}",
                "Path=/",
                f"Max-Age={DEVICE_COOKIE_MAX_AGE}",
                "SameSite=Strict",
                "HttpOnly",
            ]
            if COOKIE_SECURE:
                cookie_attrs.append("Secure")
            self.send_header(
                "Set-Cookie",
                "; ".join(cookie_attrs),
            )
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(
        self,
        status: HTTPStatus,
        message: str,
        *,
        code: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {"ok": False, "error": message}
        if code:
            payload["code"] = code
        if extra:
            payload.update(extra)
        self.send_json(payload, status=status)


def get_job(job_id: str) -> WebJob | None:
    with JOBS_LOCK:
        return JOBS.get(job_id)


class WebThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True



def main() -> None:
    parser = argparse.ArgumentParser(description="PayPal Billing Agreement Web UI Public Release")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=8080, help="监听端口，默认 8080")
    args = parser.parse_args()

    configure_logging()
    STATIC_DIR.mkdir(exist_ok=True)

    if PRODUCTION_MODE and not COOKIE_SECURE:
        logger.warning("生产模式建议设置 PAYPAL_WEB_COOKIE_SECURE=1，并通过 HTTPS 反向代理访问。")
    if not ALLOW_DEBUG_LOGS:
        logger.info("DEBUG 日志已在网页端关闭；设置 PAYPAL_WEB_ALLOW_DEBUG_LOGS=1 才允许显示。")

    server = WebThreadingHTTPServer((args.host, args.port), WebHandler)
    url_host = "localhost" if args.host in {"127.0.0.1", "0.0.0.0"} else args.host
    logger.info("Web UI running: http://{}:{}", url_host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping Web UI...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
