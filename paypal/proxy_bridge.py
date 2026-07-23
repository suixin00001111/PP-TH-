# -*- coding: utf-8 -*-
"""Local HTTP CONNECT proxy that tunnels via upstream SOCKS5(+auth).

Playwright/Chromium cannot use SOCKS5 with username/password. HTTP clients may
still use the upstream socks5 URL directly.
"""
from __future__ import annotations

import select
import socket
import struct
import threading
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit


class ProxyBridgeError(RuntimeError):
    pass


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < n:
        part = sock.recv(n - len(chunks))
        if not part:
            raise ProxyBridgeError("upstream closed during SOCKS handshake")
        chunks.extend(part)
    return bytes(chunks)


def open_socks5_tcp(
    *,
    proxy_host: str,
    proxy_port: int,
    username: str,
    password: str,
    dest_host: str,
    dest_port: int,
    timeout: float = 20.0,
) -> socket.socket:
    sock = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
    sock.settimeout(timeout)
    try:
        if username or password:
            sock.sendall(b"\x05\x01\x02")
        else:
            sock.sendall(b"\x05\x01\x00")
        resp = _recv_exact(sock, 2)
        if resp[0] != 5:
            raise ProxyBridgeError(f"bad SOCKS version: {resp!r}")
        method = resp[1]
        if method == 2:
            user_b = (username or "").encode("utf-8")
            pass_b = (password or "").encode("utf-8")
            if len(user_b) > 255 or len(pass_b) > 255:
                raise ProxyBridgeError("SOCKS username/password too long")
            sock.sendall(
                b"\x01"
                + bytes([len(user_b)])
                + user_b
                + bytes([len(pass_b)])
                + pass_b
            )
            auth = _recv_exact(sock, 2)
            if auth[1] != 0:
                raise ProxyBridgeError("SOCKS5 authentication failed")
        elif method != 0:
            raise ProxyBridgeError(f"SOCKS5 method not accepted: {method}")

        host_b = dest_host.encode("idna")
        if len(host_b) > 255:
            raise ProxyBridgeError("destination host too long")
        req = (
            b"\x05\x01\x00\x03"
            + bytes([len(host_b)])
            + host_b
            + struct.pack("!H", dest_port)
        )
        sock.sendall(req)
        hdr = _recv_exact(sock, 4)
        if hdr[0] != 5 or hdr[1] != 0:
            raise ProxyBridgeError(f"SOCKS5 connect failed status={hdr[1]}")
        atyp = hdr[3]
        if atyp == 1:
            _recv_exact(sock, 4 + 2)
        elif atyp == 3:
            ln = _recv_exact(sock, 1)[0]
            _recv_exact(sock, ln + 2)
        elif atyp == 4:
            _recv_exact(sock, 16 + 2)
        else:
            raise ProxyBridgeError(f"SOCKS5 unknown atyp={atyp}")
        sock.settimeout(None)
        return sock
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        raise


def _pipe(a: socket.socket, b: socket.socket) -> None:
    try:
        while True:
            readable, _, _ = select.select([a, b], [], [], 300)
            if not readable:
                break
            for src in readable:
                dst = b if src is a else a
                data = src.recv(65536)
                if not data:
                    return
                dst.sendall(data)
    except Exception:
        return
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                s.close()
            except Exception:
                pass


@dataclass
class LocalHttpToSocksBridge:
    """HTTP proxy on 127.0.0.1 that forwards via upstream SOCKS5."""

    listen_host: str = "127.0.0.1"
    upstream_host: str = ""
    upstream_port: int = 0
    username: str = ""
    password: str = ""
    _sock: socket.socket | None = None
    _thread: threading.Thread | None = None
    _stop: threading.Event = field(default_factory=threading.Event)

    @property
    def port(self) -> int:
        if not self._sock:
            return 0
        return int(self._sock.getsockname()[1])

    @property
    def http_proxy_url(self) -> str:
        return f"http://{self.listen_host}:{self.port}"

    def start(self) -> str:
        if self._sock is not None:
            return self.http_proxy_url
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.listen_host, 0))
        srv.listen(64)
        srv.settimeout(1.0)
        self._sock = srv
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._serve, name="http-socks-bridge", daemon=True
        )
        self._thread.start()
        return self.http_proxy_url

    def stop(self) -> None:
        self._stop.set()
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        thr = self._thread
        if thr and thr.is_alive():
            thr.join(timeout=2.0)
        self._thread = None

    def _serve(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                client, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle_client, args=(client,), daemon=True
            ).start()

    def _handle_client(self, client: socket.socket) -> None:
        upstream: socket.socket | None = None
        try:
            client.settimeout(30.0)
            data = b""
            while b"\r\n\r\n" not in data and len(data) < 65536:
                chunk = client.recv(4096)
                if not chunk:
                    return
                data += chunk
            header = data.split(b"\r\n\r\n", 1)[0].decode(
                "iso-8859-1", errors="replace"
            )
            lines = header.split("\r\n")
            if not lines:
                return
            parts = lines[0].split()
            if len(parts) < 3:
                client.sendall(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
                return
            method, target = parts[0].upper(), parts[1]
            if method != "CONNECT":
                client.sendall(
                    b"HTTP/1.1 405 Method Not Allowed\r\nConnection: close\r\n\r\n"
                )
                return
            if ":" not in target:
                client.sendall(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
                return
            host, port_s = target.rsplit(":", 1)
            dest_port = int(port_s)
            upstream = open_socks5_tcp(
                proxy_host=self.upstream_host,
                proxy_port=self.upstream_port,
                username=self.username,
                password=self.password,
                dest_host=host,
                dest_port=dest_port,
            )
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            client.settimeout(None)
            _pipe(client, upstream)
            upstream = None
        except Exception:
            try:
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            except Exception:
                pass
        finally:
            try:
                client.close()
            except Exception:
                pass
            if upstream is not None:
                try:
                    upstream.close()
                except Exception:
                    pass


def bridge_from_proxy_url(proxy_url: str) -> LocalHttpToSocksBridge:
    parsed = urlsplit(proxy_url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"socks5", "socks5h"}:
        raise ProxyBridgeError(f"bridge requires socks5 upstream, got {scheme or '?'}")
    if not parsed.hostname or not parsed.port:
        raise ProxyBridgeError("socks5 upstream must include host and port")
    bridge = LocalHttpToSocksBridge(
        upstream_host=parsed.hostname,
        upstream_port=int(parsed.port),
        username=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
    )
    bridge.start()
    return bridge
