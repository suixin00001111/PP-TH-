"""Ensure TLS CA bundle is reachable by native curl (curl_cffi).

curl on Windows fails with error 77 when the certifi path contains non-ASCII
characters (common with Chinese Windows usernames). Mirror the PEM to an
ASCII-only location and point SSL_CERT_FILE / CURL_CA_BUNDLE at it.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_APPLIED = False
_CA_PATH: str = ""


def _is_mostly_ascii(path: str) -> bool:
    try:
        path.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def ensure_ssl_cert_env(*, force: bool = False) -> str:
    """Return the CA file path used for TLS; set process env when needed."""
    global _APPLIED, _CA_PATH
    if _APPLIED and not force and _CA_PATH:
        return _CA_PATH

    try:
        import certifi

        src = Path(certifi.where())
    except Exception:
        src = Path()

    existing = (
        os.environ.get("SSL_CERT_FILE")
        or os.environ.get("CURL_CA_BUNDLE")
        or os.environ.get("REQUESTS_CA_BUNDLE")
        or ""
    ).strip()
    if existing and Path(existing).is_file() and _is_mostly_ascii(existing):
        _CA_PATH = existing
        _APPLIED = True
        return _CA_PATH

    if not src.is_file():
        _CA_PATH = existing
        _APPLIED = True
        return _CA_PATH

    # Prefer keeping certifi path when it is already ASCII-safe.
    if _is_mostly_ascii(str(src)):
        ca_path = str(src)
    else:
        candidates = [
            Path(os.environ.get("PROGRAMDATA") or r"C:\ProgramData") / "PP-TH" / "cacert.pem",
            Path(os.environ.get("PUBLIC") or r"C:\Users\Public") / "PP-TH" / "cacert.pem",
            Path(tempfile.gettempdir()) / "pp-th-cacert.pem",
        ]
        ca_path = ""
        last_error: Exception | None = None
        for dst in candidates:
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                # Refresh when missing or size differs (certifi updates).
                if (not dst.is_file()) or dst.stat().st_size != src.stat().st_size:
                    shutil.copyfile(src, dst)
                ca_path = str(dst)
                break
            except Exception as exc:  # pragma: no cover - FS permission edge
                last_error = exc
                continue
        if not ca_path:
            # Last resort: still point at source; caller may fall back to httpx.
            ca_path = str(src)
            if last_error:
                pass

    for key in ("SSL_CERT_FILE", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE"):
        os.environ[key] = ca_path

    _CA_PATH = ca_path
    _APPLIED = True
    return _CA_PATH
