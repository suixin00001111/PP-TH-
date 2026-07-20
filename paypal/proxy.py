"""Proxy helpers for outbound HTTP requests.

Supported formats (provider UI style):
  1) hostname:port:username:password
  2) socks5://username:password@host:port   (also http/https/socks5h)
  3) username:password@hostname:port
  4) hostname:port@username:password
  5) http://127.0.0.1:7897                  (local Clash mixed, no auth)
  6) host:port                              (local no-auth shortcut)
"""
from __future__ import annotations

import os
import random
import sys
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import quote, unquote, urlsplit

from config import PROXY_POOL, PROXY_ENABLED

try:
    from config import USE_SYSTEM_PROXY as _CFG_USE_SYSTEM_PROXY
except Exception:  # pragma: no cover
    _CFG_USE_SYSTEM_PROXY = True

_TRUE_VALUES = {"1", "true", "yes", "on", "enable", "enabled", "y"}
_FALSE_VALUES = {"0", "false", "no", "off", "disable", "disabled", "n", ""}


def _valid_port(text: str) -> int | None:
    try:
        port = int(str(text).strip())
    except ValueError:
        return None
    if 1 <= port <= 65535:
        return port
    return None


@dataclass(frozen=True)
class ProxyEntry:
    host: str
    port: int
    username: str = ""
    password: str = ""
    scheme: str = "http"

    @classmethod
    def parse(cls, raw: str) -> "ProxyEntry":
        value = (raw or "").strip()
        if not value:
            raise ValueError("代理配置为空")

        # scheme URL: socks5://user:pass@host:port / http://127.0.0.1:7897
        if "://" in value:
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https", "socks5", "socks5h"}:
                raise ValueError(f"不支持的代理协议：{parsed.scheme}")
            if not parsed.hostname or not parsed.port:
                raise ValueError("代理 URL 必须包含 host 和 port")
            return cls(
                host=parsed.hostname,
                port=int(parsed.port),
                username=unquote(parsed.username or ""),
                password=unquote(parsed.password or ""),
                scheme=parsed.scheme.lower(),
            )

        # Forms with '@'
        if "@" in value:
            left, right = value.rsplit("@", 1)
            left = left.strip()
            right = right.strip()

            # hostname:port@username:password
            if ":" in left:
                host, port_text = left.rsplit(":", 1)
                port = _valid_port(port_text)
                if port is not None and ":" in right:
                    username, password = right.split(":", 1)
                    if host.strip() and username.strip() and password.strip():
                        return cls(
                            host=host.strip(),
                            port=port,
                            username=username.strip(),
                            password=password.strip(),
                            scheme="http",
                        )

            # username:password@hostname:port
            if ":" in left and ":" in right:
                username, password = left.split(":", 1)
                host, port_text = right.rsplit(":", 1)
                port = _valid_port(port_text)
                if port is not None and host.strip() and username.strip() and password.strip():
                    return cls(
                        host=host.strip(),
                        port=port,
                        username=username.strip(),
                        password=password.strip(),
                        scheme="http",
                    )

            raise ValueError(
                "带 @ 的代理格式应为 user:pass@host:port 或 host:port@user:pass"
            )

        # host:port (local no-auth, e.g. 127.0.0.1:7897)
        if value.count(":") == 1:
            host, port_text = value.split(":", 1)
            port = _valid_port(port_text)
            if port is not None and host.strip():
                return cls(host=host.strip(), port=port, username="", password="", scheme="http")

        # hostname:port:username:password  (password may contain ':')
        parts = value.split(":", 3)
        if len(parts) == 4:
            host, port_text, username, password = [p.strip() for p in parts]
            port = _valid_port(port_text)
            if port is None:
                raise ValueError("代理 port 必须是 1-65535")
            if not host:
                raise ValueError("代理 host 不能为空")
            if not username or not password:
                raise ValueError("代理 username/password 不能为空")
            return cls(
                host=host,
                port=port,
                username=username,
                password=password,
                scheme="http",
            )

        raise ValueError(
            "代理格式应为以下之一："
            "host:port:user:pass | user:pass@host:port | "
            "host:port@user:pass | host:port | "
            "http://127.0.0.1:7897 | socks5://user:pass@host:port"
        )

    @property
    def url(self) -> str:
        if self.username or self.password:
            user = quote(self.username, safe="")
            password = quote(self.password, safe="")
            auth = f"{user}:{password}@"
        else:
            auth = ""
        return f"{self.scheme}://{auth}{self.host}:{self.port}"

    @property
    def masked(self) -> str:
        auth = "***:***@" if self.username or self.password else ""
        return f"{self.scheme}://{auth}{self.host}:{self.port}"


@dataclass(frozen=True)
class ProxyConfig:
    enabled: bool
    entry: ProxyEntry | None = None

    @property
    def url(self) -> str | None:
        return self.entry.url if self.enabled and self.entry else None

    @property
    def label(self) -> str:
        if not self.enabled or not self.entry:
            return "代理关闭"
        return self.entry.masked


def parse_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return default


def _split_pool(raw: str) -> list[str]:
    lines: list[str] = []
    for item in (raw or "").replace(",", "\n").splitlines():
        item = item.strip()
        if item and not item.startswith("#"):
            lines.append(item)
    return lines


def _read_windows_system_proxy() -> str | None:
    """Read WinINET user proxy (Clash/V2Ray system proxy mode)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        ) as key:
            enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            if not int(enable):
                return None
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
    except OSError:
        return None

    server = (server or "").strip()
    if not server:
        return None

    # forms: host:port | http=host:port;https=host:port | socks=host:port
    if "=" in server or ";" in server:
        mapping: dict[str, str] = {}
        for part in server.split(";"):
            part = part.strip()
            if not part:
                continue
            if "=" in part:
                scheme, endpoint = part.split("=", 1)
                mapping[scheme.strip().lower()] = endpoint.strip()
            else:
                mapping["http"] = part
        endpoint = (
            mapping.get("https")
            or mapping.get("http")
            or mapping.get("socks")
            or mapping.get("socks5")
        )
        if not endpoint:
            return None
        if "://" not in endpoint:
            scheme = "socks5" if mapping.get("socks") or mapping.get("socks5") else "http"
            endpoint = f"{scheme}://{endpoint}"
        return endpoint

    if "://" not in server:
        return f"http://{server}"
    return server


def _env_proxy_url() -> str | None:
    for name in (
        "PAYPAL_PROXY_URL",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "ALL_PROXY",
        "https_proxy",
        "http_proxy",
        "all_proxy",
    ):
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return None


def load_proxy_pool() -> list[str]:
    """Load proxy lines: PAYPAL_PROXY_POOL > PAYPAL_PROXY_URL > optional system > config.

    When USE_SYSTEM_PROXY/PAYPAL_USE_SYSTEM_PROXY is False, never fall back to
    WinINET / HTTP(S)_PROXY (local Clash). Residential pool in config is used.
    """
    env_pool = _split_pool(os.getenv("PAYPAL_PROXY_POOL", ""))
    if env_pool:
        return env_pool

    # Explicit single residential/upstream URL.
    explicit = (os.getenv("PAYPAL_PROXY_URL") or "").strip()
    if explicit:
        return [explicit]

    use_system = parse_bool(os.getenv("PAYPAL_USE_SYSTEM_PROXY"), _CFG_USE_SYSTEM_PROXY)
    if use_system:
        # only when explicitly allowed — local Clash/system proxy path
        system_proxy = _env_proxy_url() or _read_windows_system_proxy()
        if system_proxy:
            return [system_proxy]

    # never use system proxy here when disabled
    return [line.strip() for line in PROXY_POOL if str(line).strip()]


def choose_proxy_entry(pool: Iterable[str] | None = None, index: int | None = None) -> ProxyEntry:
    entries = list(pool if pool is not None else load_proxy_pool())
    if not entries:
        raise ValueError("未配置代理池")
    if index is not None:
        if index < 0 or index >= len(entries):
            raise ValueError(f"代理序号超出范围：{index}，可用范围 0-{len(entries) - 1}")
        raw = entries[index]
    else:
        raw = random.choice(entries)
    return ProxyEntry.parse(raw)


def build_proxy_config(
    enabled: bool | None = None,
    index: int | None = None,
    raw: str | None = None,
) -> ProxyConfig:
    """Return a selected proxy config.

    enabled=None means use config/env default.  If disabled, no proxy is selected.
    raw: optional user-provided proxy string (host:port:user:pass / URL forms).
         When non-empty, it always wins over the configured pool.
    """
    raw_value = (raw or "").strip()
    if raw_value:
        # Explicit user/API proxy always enables and does not touch server pool secrets.
        return ProxyConfig(enabled=True, entry=ProxyEntry.parse(raw_value))

    if enabled is None:
        should_enable = parse_bool(os.getenv("PAYPAL_PROXY_ENABLED"), PROXY_ENABLED)
    else:
        should_enable = bool(enabled)
    if not should_enable:
        return ProxyConfig(enabled=False)
    return ProxyConfig(enabled=True, entry=choose_proxy_entry(index=index))