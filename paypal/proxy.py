"""Proxy helpers for outbound HTTP requests.

Supported formats:
  1) hostname:port:username:password
  2) socks5://username:password@host:port   (also http/https/socks5h)
  3) username:password@hostname:port
  4) hostname:port@username:password
  5) http://127.0.0.1:7897
  6) host:port
"""
from __future__ import annotations
from pathlib import Path

import os
import random
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import quote, unquote, urlsplit

from config import PROXY_POOL, PROXY_ENABLED


def _load_dotenv_value(name: str) -> str:
    """Read env first, then optional .env file (BR-compatible helper)."""
    import os
    val = (os.getenv(name) or "").strip()
    if val:
        return val
    try:
        root = Path(__file__).resolve().parents[1]
        env_path = root / ".env"
        if not env_path.is_file():
            return ""
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == name:
                return v.strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""



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
            raise ValueError("proxy config is empty")

        if "://" in value:
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https", "socks5", "socks5h"}:
                raise ValueError(f"unsupported proxy scheme: {parsed.scheme}")
            if not parsed.hostname or not parsed.port:
                raise ValueError("proxy URL must include host and port")
            return cls(
                host=parsed.hostname,
                port=int(parsed.port),
                username=unquote(parsed.username or ""),
                password=unquote(parsed.password or ""),
                scheme=parsed.scheme.lower(),
            )

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

            raise ValueError("proxy with @ must be user:pass@host:port or host:port@user:pass")

        # host:port
        if value.count(":") == 1:
            host, port_text = value.split(":", 1)
            port = _valid_port(port_text)
            if port is not None and host.strip():
                return cls(host=host.strip(), port=port, username="", password="", scheme="http")

        # hostname:port:username:password (password may contain ':')
        parts = value.split(":", 3)
        if len(parts) == 4:
            host, port_text, username, password = [p.strip() for p in parts]
            port = _valid_port(port_text)
            if port is not None and host and username and password:
                return cls(host=host, port=port, username=username, password=password, scheme="http")

        raise ValueError(
            "unsupported proxy format; use host:port:user:pass, user:pass@host:port, or scheme://user:pass@host:port"
        )

    @property
    def url(self) -> str:
        if self.username:
            user = quote(self.username, safe="")
            password = quote(self.password, safe="")
            auth = f"{user}:{password}@"
        else:
            auth = ""
        return f"{self.scheme}://{auth}{self.host}:{self.port}"

    @property
    def label(self) -> str:
        if self.username:
            return f"{self.scheme}://{self.username}:***@{self.host}:{self.port}"
        return f"{self.scheme}://{self.host}:{self.port}"

    def with_scheme(self, scheme: str) -> "ProxyEntry":
        scheme_n = (scheme or "http").strip().lower() or "http"
        if scheme_n not in {"http", "https", "socks5", "socks5h"}:
            raise ValueError(f"unsupported proxy scheme: {scheme_n}")
        return ProxyEntry(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            scheme=scheme_n,
        )


@dataclass(frozen=True)
class ProxyConfig:
    enabled: bool
    entry: ProxyEntry | None = None
    resolved_from: str = ""

    @property
    def url(self) -> str | None:
        if not self.enabled or self.entry is None:
            return None
        return self.entry.url

    @property
    def label(self) -> str:
        if not self.enabled or self.entry is None:
            return "proxy disabled"
        base = self.entry.label
        if self.resolved_from and self.resolved_from != (self.entry.scheme or ""):
            return f"{base} (auto {self.entry.scheme} from {self.resolved_from})"
        return base

    def with_entry(self, entry: ProxyEntry, *, resolved_from: str = "") -> "ProxyConfig":
        return ProxyConfig(
            enabled=True,
            entry=entry,
            resolved_from=resolved_from or self.resolved_from,
        )




def candidate_proxy_entries(entry: ProxyEntry) -> list[ProxyEntry]:
    """Same host/user/pass as user filled; try schemes residential nodes often accept.

    cliproxy and similar providers frequently accept SOCKS5 on the same port while
    HTTP CONNECT is aborted from some networks. Prefer socks5h so DNS also goes
    through the proxy when system DNS/TUN is unavailable.
    """
    preferred = (entry.scheme or "http").lower()
    if preferred in {"socks5h", "socks5"}:
        ordered = ["socks5h", "socks5", "http", "https"]
    else:
        ordered = ["socks5h", "socks5", preferred, "http", "https"]
    seen: set[str] = set()
    out: list[ProxyEntry] = []
    for scheme in ordered:
        if scheme in seen:
            continue
        seen.add(scheme)
        out.append(entry.with_scheme(scheme))
    return out




def diagnose_proxy_endpoint(entry: ProxyEntry, *, timeout: float = 8.0) -> dict[str, str]:
    """Raw TCP probe against the filled host:port (no system/TUN app proxy).

    cliproxy often replies HTTP 403 to SOCKS and CONNECT when client IP is not
    allowlisted: ``msg: forbidden ip=x.x.x.x not supported`` (curl shows as 97).
    """
    import base64
    import re as _re
    import socket

    info: dict[str, str] = {
        "host": entry.host,
        "port": str(entry.port),
        "scheme_filled": entry.scheme,
    }
    try:
        info["resolved_ip"] = socket.gethostbyname(entry.host)
    except Exception as exc:
        info["dns_error"] = str(exc)
        return info

    def _recv(sock: socket.socket, n: int = 400) -> bytes:
        sock.settimeout(timeout)
        try:
            return sock.recv(n)
        except Exception:
            return b""

    try:
        sock = socket.create_connection((entry.host, entry.port), timeout=timeout)
        try:
            sock.sendall(b"\x05\x01\x02" if (entry.username or entry.password) else b"\x05\x01\x00")
            raw = _recv(sock)
            info["socks_hello_hex"] = raw[:16].hex()
            if raw.startswith(b"HTTP") or b"forbidden" in raw.lower() or (raw[:1] not in (b"\x05", b"")):
                info["socks_hello_text"] = raw.decode("utf-8", errors="replace")[:300]
        finally:
            sock.close()
    except Exception as exc:
        info["socks_hello_error"] = str(exc)

    try:
        sock = socket.create_connection((entry.host, entry.port), timeout=timeout)
        try:
            token = base64.b64encode(f"{entry.username}:{entry.password}".encode("utf-8")).decode("ascii")
            req = (
                "CONNECT api.ipify.org:443 HTTP/1.1\r\n"
                "Host: api.ipify.org:443\r\n"
                f"Proxy-Authorization: Basic {token}\r\n"
                "\r\n"
            ).encode("ascii")
            sock.sendall(req)
            raw = _recv(sock)
            info["http_connect_text"] = raw.decode("utf-8", errors="replace")[:400]
        finally:
            sock.close()
    except Exception as exc:
        info["http_connect_error"] = str(exc)

    blob = "\n".join(
        str(info.get(k) or "")
        for k in (
            "socks_hello_text",
            "http_connect_text",
            "socks_hello_error",
            "http_connect_error",
        )
    )
    m = _re.search(r"forbidden\s+ip\s*=\s*([0-9.]+)\s*not supported", blob, _re.I)
    if m:
        info["forbidden_ip"] = m.group(1)
        info["provider_block"] = "ip_not_supported"
    elif "forbidden" in blob.lower() and "ip" in blob.lower():
        info["provider_block"] = "forbidden_ip"
    elif "407" in blob:
        info["provider_block"] = "auth_required"
    return info


def format_proxy_diagnosis(
    entry: ProxyEntry,
    diagnosis: dict[str, str],
    errors: list[str] | None = None,
) -> str:
    import re as _re

    forbidden_ip = (diagnosis or {}).get("forbidden_ip") or ""
    if not forbidden_ip:
        blob = " ".join(str(v) for v in (diagnosis or {}).values())
        m = _re.search(r"forbidden\s+ip\s*=\s*([0-9.]+)", blob, _re.I)
        if m:
            forbidden_ip = m.group(1)
    if forbidden_ip or (diagnosis or {}).get("provider_block") in {
        "ip_not_supported",
        "forbidden_ip",
    }:
        ip = forbidden_ip or "当前公网IP"
        return (
            f"代理商拒绝了你的公网 IP {ip}（forbidden ip not supported）。"
            "这与 socks5/http 填写无关：节点在握手阶段就返回 403。"
            "开 TUN 能通，是因为出口 IP 变成了隧道 IP，不是程序没走你填的代理。"
            "处理（二选一）："
            f"1) 登录 cliproxy 后台，把 {ip} 加入 IP 白名单后再关 TUN 测试；"
            "2) 继续开 TUN（可清空代理框，或仍填代理但源 IP 已是隧道出口）。"
            "程序无法在被拒绝的源 IP 上绕过代理商限制。"
        )
    detail = " | ".join((errors or [])[-4:]) if errors else ""
    socks_txt = (diagnosis or {}).get("socks_hello_text") or ""
    http_txt = (diagnosis or {}).get("http_connect_text") or ""
    extra = (socks_txt or http_txt or "")[:180]
    if extra:
        detail = f"{detail} | raw: {extra}".strip(" |")
    return (
        "填写的代理不可用（仅使用你填写的主机/端口/账号，已自动尝试 socks5h/socks5/http）。"
        + (f" 详情: {detail[:500]}" if detail else "")
    )


def resolve_working_proxy_entry(
    entry: ProxyEntry,
    *,
    timeout: float = 12.0,
    test_url: str = "https://api.ipify.org?format=json",
) -> tuple[ProxyEntry, str, int]:
    """Probe candidate schemes; return (entry, exit_ip, latency_ms)."""
    import time

    try:
        from curl_cffi import requests as curl_requests
    except Exception as exc:  # pragma: no cover
        raise ValueError(f"proxy probe dependency unavailable: {exc}") from exc

    errors: list[str] = []
    diagnosis = diagnose_proxy_endpoint(entry)
    if diagnosis.get("forbidden_ip") or diagnosis.get("provider_block") in {
        "ip_not_supported",
        "forbidden_ip",
    }:
        raise ValueError(format_proxy_diagnosis(entry, diagnosis, errors))
    for candidate in candidate_proxy_entries(entry):
        proxy_url = candidate.url
        started = time.time()
        try:
            with curl_requests.Session(timeout=timeout, impersonate="chrome131") as client:
                if hasattr(client, "trust_env"):
                    client.trust_env = False
                client.proxies = {"http": proxy_url, "https": proxy_url}
                resp = client.get(test_url)
                status = int(getattr(resp, "status_code", 0) or 0)
                body = (getattr(resp, "text", None) or "")[:300]
                low = body.lower()
                if status == 403 or "forbidden" in low or "not supported" in low:
                    errors.append(f"{candidate.scheme}: HTTP {status} {body[:120]}")
                    continue
                if status < 200 or status >= 400:
                    errors.append(f"{candidate.scheme}: HTTP {status}")
                    continue
                exit_ip = ""
                try:
                    exit_ip = str((resp.json() or {}).get("ip") or "").strip()
                except Exception:
                    exit_ip = body.strip()[:64]
                latency_ms = int((time.time() - started) * 1000)
                return candidate, exit_ip, latency_ms
        except Exception as exc:
            errors.append(f"{candidate.scheme}: {exc}")
            continue
    raise ValueError(format_proxy_diagnosis(entry, diagnosis, errors))




def get_system_proxy_entry() -> ProxyEntry | None:
    """Detect local system / client mixed proxy (Clash 系统代理等).

    Brazil-style runs usually go out via OS/client proxy or TUN. Our multi-country
    web previously forced a direct connection to the filled residential URL and
    scrubbed env, so cliproxy saw the raw China IP and returned forbidden.
    """
    import socket

    candidates: list[str] = []

    # 1) Windows Internet Settings (系统代理)
    try:
        system_url = _read_windows_system_proxy()
        if system_url:
            candidates.append(system_url)
    except Exception:
        pass

    # 2) Environment (if client exported HTTP_PROXY)
    env_url = _env_proxy_url()
    if env_url:
        # Prefer local loopback env proxies; skip remote env that might be stale
        candidates.append(env_url)

    # 3) Common local client ports
    for host, port, scheme in (
        ("127.0.0.1", 7897, "http"),
        ("127.0.0.1", 7890, "http"),
        ("127.0.0.1", 7891, "http"),
        ("127.0.0.1", 10809, "http"),
        ("127.0.0.1", 10808, "http"),
        ("127.0.0.1", 1080, "socks5h"),
        ("127.0.0.1", 20171, "http"),
        ("127.0.0.1", 6152, "http"),
    ):
        try:
            sock = socket.create_connection((host, port), timeout=0.25)
            sock.close()
            candidates.append(f"{scheme}://{host}:{port}")
        except Exception:
            continue

    seen: set[str] = set()
    for raw in candidates:
        raw = (raw or "").strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        try:
            entry = ProxyEntry.parse(raw if "://" in raw else f"http://{raw}")
        except Exception:
            try:
                # host:port
                if raw.count(":") == 1:
                    host, port_s = raw.split(":", 1)
                    entry = ProxyEntry(host=host.strip(), port=int(port_s), scheme="http")
                else:
                    continue
            except Exception:
                continue
        # Only accept loopback / explicit local system proxies here
        host_l = (entry.host or "").lower()
        if host_l in {"127.0.0.1", "localhost", "::1"} or host_l.startswith("127."):
            return entry
    # Non-loopback Windows proxy (rare) still usable
    try:
        system_url = _read_windows_system_proxy()
        if system_url:
            return ProxyEntry.parse(system_url if "://" in system_url else f"http://{system_url}")
    except Exception:
        pass
    return None



def _windows_system_proxy_enabled() -> bool:
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )
        enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
        return bool(int(enable))
    except Exception:
        return False


def probe_proxy_entry(
    entry: ProxyEntry,
    *,
    timeout: float = 12.0,
    test_url: str = "https://api.ipify.org?format=json",
) -> tuple[str, int]:
    """Return (exit_ip, latency_ms) or raise ValueError. Tries several clients."""
    import time

    proxy_url = entry.url
    errors: list[str] = []

    # 1) curl_cffi (primary for PayPal path)
    try:
        from curl_cffi import requests as curl_requests

        started = time.time()
        with curl_requests.Session(timeout=timeout, impersonate="chrome131") as client:
            if hasattr(client, "trust_env"):
                client.trust_env = False
            client.proxies = {"http": proxy_url, "https": proxy_url}
            resp = client.get(test_url)
            status = int(getattr(resp, "status_code", 0) or 0)
            body = (getattr(resp, "text", None) or "")[:300]
            low = body.lower()
            if status == 403 or "forbidden" in low or "not supported" in low:
                raise ValueError(f"HTTP {status} {body[:160]}")
            if status < 200 or status >= 400:
                raise ValueError(f"HTTP {status}")
            try:
                exit_ip = str((resp.json() or {}).get("ip") or "").strip()
            except Exception:
                exit_ip = body.strip()[:64]
            return exit_ip, int((time.time() - started) * 1000)
    except Exception as exc:
        errors.append(f"curl_cffi: {exc}")

    # 2) httpx
    try:
        import httpx

        started = time.time()
        with httpx.Client(proxy=proxy_url, timeout=timeout, trust_env=False) as client:
            resp = client.get(test_url)
            status = int(resp.status_code)
            body = (resp.text or "")[:300]
            low = body.lower()
            if status == 403 or "forbidden" in low or "not supported" in low:
                raise ValueError(f"HTTP {status} {body[:160]}")
            if status < 200 or status >= 400:
                raise ValueError(f"HTTP {status}")
            try:
                exit_ip = str((resp.json() or {}).get("ip") or "").strip()
            except Exception:
                exit_ip = body.strip()[:64]
            return exit_ip, int((time.time() - started) * 1000)
    except Exception as exc:
        errors.append(f"httpx: {exc}")

    # 3) requests
    try:
        import requests

        started = time.time()
        resp = requests.get(
            test_url,
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=timeout,
        )
        status = int(resp.status_code)
        body = (resp.text or "")[:300]
        low = body.lower()
        if status == 403 or "forbidden" in low or "not supported" in low:
            raise ValueError(f"HTTP {status} {body[:160]}")
        if status < 200 or status >= 400:
            raise ValueError(f"HTTP {status}")
        try:
            exit_ip = str((resp.json() or {}).get("ip") or "").strip()
        except Exception:
            exit_ip = body.strip()[:64]
        return exit_ip, int((time.time() - started) * 1000)
    except Exception as exc:
        errors.append(f"requests: {exc}")

    raise ValueError(" | ".join(errors[-3:]) if errors else "probe failed")


def resolve_outbound_proxy(
    filled_raw: str | None = None,
    *,
    allow_system_fallback: bool = True,
    timeout: float = 12.0,
) -> tuple[ProxyEntry, str, int, str]:
    """Resolve outbound proxy like Brazil daily usage + residential fill.

    Strategy (aligned with openai-paypal / Brazil ops):
      - If Windows 系统代理 is ON, try local client proxy FIRST (127.0.0.1:789x).
        Brazil runs usually ride the client/TUN path rather than raw residential.
      - Then try the user-filled residential URL (socks5h/http auto).
      - Then try system proxy again as fallback.

    Returns (entry, exit_ip, latency_ms, note).
    """
    filled_raw = (filled_raw or "").strip()
    notes: list[str] = []
    filled_entry: ProxyEntry | None = None
    system_entry = get_system_proxy_entry() if allow_system_fallback else None
    system_on = _windows_system_proxy_enabled()

    def _try_entry(entry: ProxyEntry, tag: str) -> tuple[ProxyEntry, str, int, str] | None:
        try:
            # For remote residential entries, reuse multi-scheme resolver.
            host = (entry.host or "").lower()
            is_local = host in {"127.0.0.1", "localhost", "::1"} or host.startswith("127.")
            if not is_local and entry.username:
                working, exit_ip, latency_ms = resolve_working_proxy_entry(
                    entry, timeout=timeout
                )
                return working, exit_ip, latency_ms, tag
            exit_ip, latency_ms = probe_proxy_entry(entry, timeout=timeout)
            return entry, exit_ip, latency_ms, tag
        except Exception as exc:
            notes.append(f"{tag}: {exc}")
            return None

    # 1) System first when Windows 系统代理 is enabled (Brazil-like)
    if system_entry is not None and system_on:
        hit = _try_entry(system_entry, f"system-first:{system_entry.label}")
        if hit:
            return hit

    # 2) User-filled residential / custom
    if filled_raw:
        try:
            filled_entry = ProxyEntry.parse(filled_raw)
        except Exception as exc:
            notes.append(f"parse-filled: {exc}")
            filled_entry = None
        if filled_entry is not None:
            hit = _try_entry(filled_entry, "filled")
            if hit:
                working, exit_ip, latency_ms, tag = hit
                if working.scheme != filled_entry.scheme:
                    tag = f"filled-auto-{working.scheme}"
                return working, exit_ip, latency_ms, tag

    # 3) System fallback even if ProxyEnable is off but local port is open
    if system_entry is not None:
        hit = _try_entry(system_entry, f"system-fallback:{system_entry.label}")
        if hit:
            return hit

    # Compose actionable error (Chinese)
    filled_msg = ""
    system_msg = ""
    for n in notes:
        low = n.lower()
        if "filled" in low or "forbidden ip" in low or "114." in n:
            filled_msg = n
        if "system" in low:
            system_msg = n
    if not filled_msg:
        filled_msg = next((n for n in notes if "forbidden" in n.lower() or "filled" in n.lower()), "")
    if not system_msg:
        system_msg = next((n for n in notes if "system" in n.lower()), "")

    parts = [
        "出网探测失败（已按巴西用法尝试：系统代理/填写代理）。",
    ]
    if filled_raw:
        parts.append(
            "填写的住宅代理：当前公网 IP 常被 cliproxy 拒绝（forbidden ip not supported）；"
            "关 TUN 直连节点会被拒，这与 socks5/http 写法无关。"
        )
    if system_entry is not None:
        parts.append(
            f"系统代理已检测到 {system_entry.label}，但当前无法完成 HTTPS 出网"
            "（常见：只开了系统代理开关、未开 TUN，或客户端无可用节点）。"
            "巴西项目能跑，多半是开了 TUN/虚拟网卡，流量在系统层已出网。"
        )
    else:
        parts.append("未检测到本地系统代理（Clash 系统代理未开或端口未监听）。")
    parts.append(
        "可行处理：1) 打开客户端 TUN/虚拟网卡后再跑（可清空代理框，与巴西一致）；"
        "2) 或在 cliproxy 后台把本机公网 IP 加白名单后关 TUN 用填写代理；"
        "3) 系统代理模式需客户端本身已能浏览器正常上网。"
    )
    detail = " | ".join(notes[-4:])
    if detail:
        parts.append(f"技术详情: {detail[:450]}")
    raise ValueError("".join(parts))



def scrub_process_proxy_env() -> dict[str, str]:
    keys = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "NO_PROXY",
        "no_proxy",
    )
    saved: dict[str, str] = {}
    for key in keys:
        if key in os.environ:
            saved[key] = os.environ.pop(key)
    return saved


def restore_process_proxy_env(saved: dict[str, str]) -> None:
    for key, value in (saved or {}).items():
        os.environ[key] = value


def parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return default


def _split_pool(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    parts: list[str] = []
    for chunk in text.replace("\r", "\n").replace(";", "\n").replace(",", "\n").split("\n"):
        item = chunk.strip()
        if item:
            parts.append(item)
    return parts


def _read_windows_system_proxy() -> str | None:
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
    """Load proxy lines: PAYPAL_PROXY_POOL > PAYPAL_PROXY_URL > optional system > config."""
    env_pool = _split_pool(os.getenv("PAYPAL_PROXY_POOL", ""))
    if env_pool:
        return env_pool

    explicit = (os.getenv("PAYPAL_PROXY_URL") or "").strip()
    if explicit:
        return [explicit]

    use_system = parse_bool(os.getenv("PAYPAL_USE_SYSTEM_PROXY"), _CFG_USE_SYSTEM_PROXY)
    if use_system:
        system_proxy = _env_proxy_url() or _read_windows_system_proxy()
        if system_proxy:
            return [system_proxy]

    return [line.strip() for line in PROXY_POOL if str(line).strip()]


def choose_proxy_entry(pool: Iterable[str] | None = None, index: int | None = None) -> ProxyEntry:
    entries = list(pool if pool is not None else load_proxy_pool())
    if not entries:
        raise ValueError("proxy pool is empty")
    if index is not None:
        if index < 0 or index >= len(entries):
            raise ValueError(f"proxy index out of range: {index}, valid 0-{len(entries) - 1}")
        raw = entries[index]
    else:
        raw = random.choice(entries)
    return ProxyEntry.parse(raw)


def build_proxy_config(
    enabled: bool | None = None,
    index: int | None = None,
    raw: str | None = None,
    proxy_url: str | None = None,
) -> ProxyConfig:
    """Return a selected proxy config.

    enabled=None means use config/env default. If disabled, no proxy is selected.
    raw / proxy_url: optional user-provided proxy string. When non-empty, it wins.
    """
    raw_value = (raw or proxy_url or "").strip()
    if raw_value:
        return ProxyConfig(enabled=True, entry=ProxyEntry.parse(raw_value))

    if enabled is None:
        should_enable = parse_bool(os.getenv("PAYPAL_PROXY_ENABLED"), PROXY_ENABLED)
    else:
        should_enable = bool(enabled)
    if not should_enable:
        return ProxyConfig(enabled=False)
    return ProxyConfig(enabled=True, entry=choose_proxy_entry(index=index))
