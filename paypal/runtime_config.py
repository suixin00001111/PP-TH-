"""Unified runtime + risk-mode resolution for multi-country BA flow.

Priority (highest first):
  CLI / Web job fields > profile preset > environment > config.py defaults

Coarse modes (UI/CLI --runtime):
  protocol | headless | auto | roxy

Fine modes (openai-paypal compatible, optional overrides):
  PAYPAL_FINGERPRINT_SOURCE
  PAYPAL_DATADOME_MODE
  PAYPAL_MTR_RUNTIME
  PAYPAL_RISK_SIGNALS_MODE
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any

_TRUE = {"1", "true", "yes", "on", "enable", "enabled", "y"}
_FALSE = {"0", "false", "no", "off", "disable", "disabled", "n", ""}

COARSE_MODES = ("protocol", "headless", "auto", "roxy")
PROFILES = ("test", "real")


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    text = str(raw).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return default


def _cfg(name: str, default: Any = None) -> Any:
    try:
        import config as cfg
        return getattr(cfg, name, default)
    except Exception:
        return default


def normalize_coarse_mode(raw: str | None) -> str:
    text = (raw or "").strip().lower().replace("-", "_")
    if text in {"", "default"}:
        return ""
    if text in {"protocol", "http", "pure", "python", "python_generated"}:
        return "protocol"
    if text in {"headless", "playwright", "local_headless", "local_playwright"}:
        return "headless"
    if text in {"roxy", "browser"}:
        return "roxy"
    if text in {"auto", "automatic"}:
        return "auto"
    return "protocol" if text else ""


def normalize_profile(raw: str | None) -> str:
    text = (raw or "").strip().lower()
    if text in {"test", "smoke", "dry", "protocol_test"}:
        return "test"
    if text in {"real", "prod", "production", "live"}:
        return "real"
    return ""


def has_roxy_key() -> bool:
    if _env("PAYPAL_ROXY_API_KEY") or _env("ROXY_API_KEY"):
        return True
    return bool(str(_cfg("ROXY_API_KEY", "") or "").strip())


def map_coarse_to_fine(coarse: str) -> dict[str, str]:
    """Map one coarse runtime to fingerprint/datadome/mtr/risk modes."""
    mode = normalize_coarse_mode(coarse) or "protocol"
    if mode == "protocol":
        return {
            "fingerprint_source": "random",
            "datadome_mode": "protocol",
            "mtr_runtime": "python_generated",
            "risk_signals_mode": "protocol",
        }
    if mode == "headless":
        return {
            "fingerprint_source": "headless",
            "datadome_mode": "headless",
            "mtr_runtime": "headless",
            "risk_signals_mode": "headless",
        }
    if mode == "roxy":
        return {
            "fingerprint_source": "roxy",
            "datadome_mode": "roxy",
            "mtr_runtime": "roxy",
            "risk_signals_mode": "roxy",
        }
    # auto: keep fine modes on auto so libraries can pick engine
    return {
        "fingerprint_source": "auto",
        "datadome_mode": "auto",
        "mtr_runtime": "auto",
        "risk_signals_mode": "auto",
    }


def profile_defaults(profile: str) -> dict[str, Any]:
    """Scenario defaults: test = pure protocol smoke; real = browser-capable."""
    if profile == "test":
        return {
            "runtime_mode": "protocol",
            "continue_merchant": False,
            "traffic_record": False,
        }
    # real
    return {
        "runtime_mode": "auto",
        "continue_merchant": False,
        "traffic_record": False,
    }


@dataclass
class ResolvedRuntime:
    profile: str
    runtime_mode: str
    browser_engine: str
    fingerprint_source: str
    datadome_mode: str
    mtr_runtime: str
    risk_signals_mode: str
    continue_merchant: bool = False
    traffic_record: bool = False
    notes: list[str] = field(default_factory=list)

    def as_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


def effective_browser_engine(runtime_mode: str) -> str:
    mode = normalize_coarse_mode(runtime_mode) or "protocol"
    if mode == "protocol":
        return "protocol"
    if mode == "roxy":
        return "roxy" if has_roxy_key() else "headless"
    if mode == "headless":
        return "headless"
    # auto
    return "roxy" if has_roxy_key() else "headless"


def _pick(explicit: str | None, *fallbacks: str) -> str:
    for item in (explicit, *fallbacks):
        text = (item or "").strip()
        if text:
            return text
    return ""


def resolve_runtime(
    *,
    runtime_mode: str | None = None,
    profile: str | None = None,
    fingerprint_source: str | None = None,
    datadome_mode: str | None = None,
    mtr_runtime: str | None = None,
    risk_signals_mode: str | None = None,
    continue_merchant: bool | None = None,
    traffic_record: bool | None = None,
) -> ResolvedRuntime:
    notes: list[str] = []

    prof = normalize_profile(profile) or normalize_profile(_env("PAYPAL_RUN_PROFILE")) or normalize_profile(
        str(_cfg("RUN_PROFILE", "") or "")
    )
    if not prof:
        # Prefer real when default runtime is browser-capable; else test.
        cfg_mode = normalize_coarse_mode(str(_cfg("RUNTIME_MODE", "auto") or "auto")) or "auto"
        prof = "test" if cfg_mode == "protocol" else "real"
        notes.append(f"profile_inferred={prof}")

    presets = profile_defaults(prof)

    coarse = normalize_coarse_mode(runtime_mode)
    if not coarse:
        coarse = normalize_coarse_mode(_env("PAYPAL_RUNTIME_MODE") or _env("RUNTIME_MODE"))
    if not coarse:
        coarse = normalize_coarse_mode(str(presets.get("runtime_mode") or ""))
    if not coarse:
        coarse = normalize_coarse_mode(str(_cfg("RUNTIME_MODE", "auto") or "auto")) or "auto"

    mapped = map_coarse_to_fine(coarse)

    # Fine overrides: explicit args > env > config > coarse map
    fp = _pick(
        fingerprint_source,
        _env("PAYPAL_FINGERPRINT_SOURCE"),
        str(_cfg("FINGERPRINT_SOURCE", "") or ""),
        mapped["fingerprint_source"],
    )
    dd = _pick(
        datadome_mode,
        _env("PAYPAL_DATADOME_MODE"),
        str(_cfg("DATADOME_MODE", "") or ""),
        mapped["datadome_mode"],
    )
    mtr = _pick(
        mtr_runtime,
        _env("PAYPAL_MTR_RUNTIME"),
        str(_cfg("MTR_RUNTIME_MODE", "") or ""),
        mapped["mtr_runtime"],
    )
    risk = _pick(
        risk_signals_mode,
        _env("PAYPAL_RISK_SIGNALS_MODE"),
        str(_cfg("RISK_SIGNALS_MODE", "") or ""),
        mapped["risk_signals_mode"],
    )

    # If coarse is protocol, force fine modes onto protocol stack unless user
    # explicitly passed non-empty fine overrides via args (already in _pick).
    if coarse == "protocol":
        # Keep protocol stack even if config still has auto leftovers,
        # unless explicit function args were provided.
        if not (fingerprint_source or "").strip():
            fp = mapped["fingerprint_source"]
        if not (datadome_mode or "").strip():
            dd = mapped["datadome_mode"]
        if not (mtr_runtime or "").strip():
            mtr = mapped["mtr_runtime"]
        if not (risk_signals_mode or "").strip():
            risk = mapped["risk_signals_mode"]

    if continue_merchant is None:
        cont = env_bool(
            "PAYPAL_CONTINUE_MERCHANT",
            bool(_cfg("CONTINUE_MERCHANT", presets.get("continue_merchant", False))),
        )
    else:
        cont = bool(continue_merchant)

    if traffic_record is None:
        tr = env_bool(
            "PAYPAL_TRAFFIC_RECORD",
            bool(_cfg("TRAFFIC_RECORD", presets.get("traffic_record", False))),
        )
    else:
        tr = bool(traffic_record)

    engine = effective_browser_engine(coarse)
    if coarse == "roxy" and engine != "roxy":
        notes.append("roxy_key_missing_fallback_headless")
    if coarse == "auto":
        notes.append(f"auto_engine={engine}")

    return ResolvedRuntime(
        profile=prof,
        runtime_mode=coarse,
        browser_engine=engine,
        fingerprint_source=(fp or "auto").strip().lower(),
        datadome_mode=(dd or "auto").strip().lower(),
        mtr_runtime=(mtr or "auto").strip().lower(),
        risk_signals_mode=(risk or "auto").strip().lower(),
        continue_merchant=cont,
        traffic_record=tr,
        notes=notes,
    )


def apply_runtime_to_environ(resolved: ResolvedRuntime) -> None:
    """Publish resolved modes so headless/roxy/mtr modules read consistent env."""
    os.environ["PAYPAL_RUNTIME_MODE"] = resolved.runtime_mode
    os.environ["PAYPAL_FINGERPRINT_SOURCE"] = resolved.fingerprint_source
    os.environ["PAYPAL_DATADOME_MODE"] = resolved.datadome_mode
    os.environ["PAYPAL_MTR_RUNTIME"] = resolved.mtr_runtime
    os.environ["PAYPAL_RISK_SIGNALS_MODE"] = resolved.risk_signals_mode
    os.environ["PAYPAL_RUN_PROFILE"] = resolved.profile
    os.environ["PAYPAL_CONTINUE_MERCHANT"] = "1" if resolved.continue_merchant else "0"
    os.environ["PAYPAL_TRAFFIC_RECORD"] = "1" if resolved.traffic_record else "0"


def resolve_and_apply(**kwargs: Any) -> ResolvedRuntime:
    resolved = resolve_runtime(**kwargs)
    apply_runtime_to_environ(resolved)
    return resolved
