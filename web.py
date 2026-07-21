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
from paypal.proxy import ProxyConfig, build_proxy_config
from paypal.regions import get_region, normalize_phone, normalize_region, list_regions_public
from paypal.b_layer_handoff import build_b_layer_evidence, persist_b_layer_evidence
from paypal.merchant_complete import complete_merchant_chain

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


def test_proxy_connectivity(proxy_raw: str) -> dict[str, Any]:
    """Probe outbound proxy with a short HTTPS request. Never logs credentials."""
    raw = (proxy_raw or "").strip()
    if not raw:
        raise ValueError("代理不能为空")
    proxy_config = build_proxy_config(enabled=True, raw=raw)
    if not proxy_config.url:
        raise ValueError("代理解析失败")
    import time as _time
    try:
        import curl_cffi.requests as curl_requests
    except Exception as exc:
        raise ValueError(f"代理测试依赖不可用: {exc}") from exc

    started = _time.time()
    exit_ip = ""
    status = 0
    try:
        with curl_requests.Session(timeout=20, impersonate="chrome131") as client:
            client.proxies = {"http": proxy_config.url, "https": proxy_config.url}
            try:
                ip_resp = client.get("https://api.ipify.org?format=json")
                if ip_resp.status_code == 200:
                    try:
                        exit_ip = str((ip_resp.json() or {}).get("ip") or "").strip()
                    except Exception:
                        exit_ip = (ip_resp.text or "").strip()[:64]
            except Exception:
                pass
            resp = client.get("https://www.paypal.com/robots.txt", allow_redirects=True)
            status = int(getattr(resp, "status_code", 0) or 0)
            if status < 200 or status >= 500:
                raise ValueError(f"目标站点返回 HTTP {status}")
    except Exception as exc:
        msg = str(exc)
        if "403" in msg and "proxy" in msg.lower():
            raise ValueError("代理拒绝连接（403），请检查账号或接入 IP 白名单") from exc
        raise ValueError(f"代理不可用：{msg}") from exc

    latency_ms = int((_time.time() - started) * 1000)
    return {
        "ok": True,
        "proxy_label": proxy_config.label,
        "status": status,
        "exit_ip": exit_ip,
        "latency_ms": latency_ms,
    }



# ----------------------------- job model -----------------------------


@dataclass
class WebJob:
    id: str
    owner_device_id: str
    ba_token: str
    phone: str
    country: str = "TH"
    runtime_mode: str = "protocol"
    smsbower_enabled: bool = False
    _smsbower_api_key: str = ""
    debug: bool = False
    max_card_attempts: int = 5
    proxy_enabled: bool = False
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
            self.result = result
            if not succeeded:
                self.error = redact_text(
                    result.get("error", "流程返回错误状态")
                    if isinstance(result, dict)
                    else "流程返回无效结果"
                )
            self.finished_at = now_ts()
            self.updated_at = now_ts()
            self.awaiting_prompt = ""
            self._condition.notify_all()

    def fail(self, exc: BaseException) -> None:
        with self._condition:
            self.status = "failed"
            self.stage = "执行失败"
            self.error = redact_text(str(exc))
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
                "smsbower_enabled": self.smsbower_enabled,
                "debug": self.debug and ALLOW_DEBUG_LOGS,
                "max_card_attempts": self.max_card_attempts,
                "proxy_enabled": self.proxy_enabled,
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
        self._set_stage("Phase 0：打开协议页")
        return super()._phase0_initial_load()

    def _phase1_risk_controls(self):
        self._set_stage("Phase 1：发送风控/指纹信号")
        return super()._phase1_risk_controls()

    def _phase2_create_account(self):
        self._set_stage("Phase 2：进入创建账号流程")
        return super()._phase2_create_account()

    def _phase3_signup_and_2fa(self):
        self._set_stage("Phase 3：短信验证与注册")
        return super()._phase3_signup_and_2fa()

    def _phase4_authorize(self):
        self._set_stage("Phase 4：最终授权")
        return super()._phase4_authorize()

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
                        f"发送验证码失败。请输入新的手机号重新发送（如 {get_region(self.job.country).phone_placeholder}）；输入 q 退出。"
                    )
                    if value.lower() in {"q", "quit", "exit"}:
                        raise RuntimeError("OTP confirmation cancelled by user") from e
                    try:
                        self._update_user_phone(value)
                        break
                    except ValueError as phone_error:
                        logger.warning("手机号无效：{}。请重新输入。", phone_error)
                continue

            logger.info("SMS verification code sent to phone: {}", self._masked_phone())

            # SMSBower auto OTP (optional) — still fall back to manual input
            provider = getattr(self, "_otp_provider", None)
            if provider is not None:
                try:
                    self.job.set_status("running", "SMSBower 自动接码中…")
                    # If provider already reserved a number matching job phone, wait;
                    # otherwise try wait_for_code only if activation stored on flow.
                    activation = getattr(self, "_smsbower_activation", None)
                    if activation is None and hasattr(provider, "reserve_number"):
                        # only reserve if job phone looks empty/synthetic — prefer user phone
                        logger.info("SMSBower provider ready; waiting for SMS on configured number channel")
                    if activation is not None and hasattr(provider, "wait_for_code"):
                        code = provider.wait_for_code(activation)
                        if code and len(code) >= 4 and code.isdigit():
                            logger.info("SMSBower code received, confirming…")
                            if self._confirm_2fa_phone_confirmation(
                                token, signup_url, auth_id, challenge_id, code
                            ):
                                return
                            logger.warning("SMSBower code rejected by PayPal; fall back to manual OTP")
                except Exception as sms_exc:
                    logger.warning("SMSBower auto OTP failed, fall back to manual: {}", sms_exc)

            while True:
                value = self._prompt_operator(
                    f"请输入6位短信验证码；如需换号，输入新手机号（如 {get_region(self.job.country).phone_placeholder}）；输入 q 退出。"
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
    proxy_enabled: bool = False,
    proxy: str = "",
    country: str = "TH",
    runtime_mode: str = "protocol",
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
    from paypal.runtime_bridge import resolve_runtime_mode
    runtime_mode = resolve_runtime_mode(runtime_mode)
    smsbower_enabled = bool(smsbower_enabled)
    smsbower_api_key = (smsbower_api_key or "").strip()
    try:
        max_card_attempts = int(max_card_attempts)
    except Exception as exc:
        raise ValueError("最大换卡次数必须是数字") from exc
    max_card_attempts = max(1, min(max_card_attempts, 20))
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
        smsbower_enabled=smsbower_enabled,
        _smsbower_api_key=smsbower_api_key,
        debug=debug,
        max_card_attempts=max_card_attempts,
        proxy_enabled=proxy_config.enabled,
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
            job.started_at = now_ts()
            job.set_status("running", "生成用户、卡片和地址")
            proxy_config = job._proxy_config or build_proxy_config(enabled=job.proxy_enabled)
            job.proxy_enabled = proxy_config.enabled
            job.proxy_label = proxy_config.label
            user = generate_user(job.phone, country=job.country)
            card = generate_card()
            address = generate_address(country=job.country)
            job.set_generated(public_generated_payload(user, card, address))

            logger.info("Web job started: {}", job.id)
            logger.info("Proxy: {}", proxy_config.label)
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

            flow = WebPayPalFlow(
                ba_token=job.ba_token,
                user=user,
                card=card,
                address=address,
                max_card_attempts=job.max_card_attempts,
                proxy_config=proxy_config,
                runtime_mode=getattr(job, "runtime_mode", "protocol"),
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
                merchant = complete_merchant_chain(
                    result,
                    proxies=[proxy_config.url] if proxy_config.url else None,
                    log=lambda message: job.add_log("INFO", message),
                    session_path=str(job_dir / "merchant_session.json"),
                )
                result["merchant_chain"] = merchant
                result["merchant_chain_status"] = merchant.get("merchant_chain_status", "")
                result["settlement_status"] = merchant.get("settlement_status", "")
                result["session_cookies"] = merchant.get("session_cookies", result.get("session_cookies", []))
                result["b_layer"] = build_b_layer_evidence({**result, **merchant})
            job.complete(result)
        except BaseException as exc:  # keep worker alive and expose details in UI
            logger.error("Web job failed: {}", redact_text(exc))
            job.fail(exc)
        finally:
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
            return self.send_json({"regions": list_regions_public(), "default": "TH"})
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
                    str(data.get("proxy") or data.get("proxy_url") or data.get("proxy_raw") or "")
                )
                return self.send_json(result)
            except Exception as exc:
                return self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

        if path == "/api/jobs":
            if not self.check_rate_limit("job_create", limit=20, window_seconds=600):
                return
            try:
                data = self.read_json()
                job = create_job(
                    owner_device_id=self.get_device_id(),
                    ba_token=data.get("ba_token", ""),
                    phone=data.get("phone", ""),
                    debug=bool(data.get("debug", False)),
                    max_card_attempts=int(data.get("max_card_attempts", 5) or 5),
                    proxy_enabled=bool(data.get("proxy_enabled", False)),
                    proxy=str(
                        data.get("proxy")
                        or data.get("proxy_url")
                        or data.get("proxy_raw")
                        or ""
                    ),
                    country=str(data.get("country") or data.get("region") or "TH"),
                    runtime_mode=str(data.get("runtime_mode") or data.get("runtime") or "protocol"),
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
