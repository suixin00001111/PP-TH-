# 代理说明（PP Multi）

更新：2026-08-10  

本文说明当前代码的**出网解析逻辑**、与巴西项目的差异、常见故障（cliproxy / TUN / 半开 Clash / TLS）。

## 1. 设计目标

1. **优先使用你在 Web 填写的代理**（主机 / 端口 / 账号 / 密码不变）。
2. **不依赖 TUN 才能识别填写的代理**：对住宅节点自动尝试 `socks5h` / `socks5` / `http`。
3. **未填代理 URL 时允许直连**：不因本机半坏 Clash「系统代理」硬失败（巴西式：能跑先跑）。
4. **只有填了代理 URL 才 `require_proxy=True`**：探测失败才硬停，并给出可操作中文提示。
5. **错误分类要准**：真正的 `forbidden ip=…` 才报白名单；curl 35/77 分别报 TLS/CA，避免误导。

## 2. 支持的填写格式

```text
host:port:username:password
username:password@host:port
http://user:pass@host:port
socks5://user:pass@host:port
socks5h://user:pass@host:port
host:port
```

- 无 scheme 时按 `http://` 解析（住宅节点往往会再自动升到 `socks5h`）。
- **不要**写成 `http://host:port:user:pass`。
- **不要**把真实代理账号提交进 Git。

## 3. 解析顺序（`paypal/proxy.py` → `resolve_outbound_proxy`）

| 顺序 | 条件 | 行为 |
|------|------|------|
| 0 | **未填 URL** 且 `require_proxy=False` 且未开系统代理 assist | 立即 **direct**（不探 7897） |
| 1 | Web/CLI **填写了**代理 | 对同一 host/user/pass 尝试 `socks5h` → `socks5` → `http` → `https` |
| 2 | 填写失败 / 需要 assist | 再试系统/本地客户端（如 `127.0.0.1:7897`），且必须 HTTPS 探通 |
| 3 | 仍失败 | `require_proxy=True` → 中文 `ValueError`；否则返回 direct |

**Web runner 规则**（`web.py`）：

- `require_proxy = bool(filled_raw)` —— **只有粘贴了代理字符串才硬要求**
- 仅勾选「启用代理」但框为空：前端会拦；若绕过 API，后端按未填处理可直连

成功后任务日志会出现类似：

```text
Proxy resolved for job: socks5h://user:***@us.cliproxy.io:3010 exit_ip=213.x.x.x note=filled-auto-socks5h
HTTP outbound proxy: socks5h://user:***@us.cliproxy.io:3010
```

无代理冒烟：

```text
Proxy resolved for job: proxy disabled ... note=direct require_proxy=False
--- Phase 0: Initial page load ---
Page loaded: 200
```

## 4. 为什么 cliproxy 填 http 会挂、socks5h 能通？

部分网络下，同一 `host:port:user:pass`：

- `HTTP CONNECT` → `403` / 隧道失败
- `SOCKS5` 握手若被拒，有时返回 **HTTP 403 正文** → curl **(97) invalid SOCKS5 version**
- 正文里常见：`msg: forbidden ip=x.x.x.x not supported`

代码会：

1. TCP 探测读出 `forbidden ip=...`
2. 自动改用 `socks5h`（若节点支持）
3. 仍被拒则提示加白名单或改用 TUN / 系统代理路径

### 开 TUN 为什么突然能通？

TUN 改变的是**本机出口 IP**。cliproxy 放行的是**隧道出口 IP**，不是程序改写了代理字符串。  
**关 TUN + 未白名单本机公网 IP** 时，直连 cliproxy 仍可能 403。

## 5. Headless / Playwright 与 SOCKS 认证

Chromium **不支持带用户名密码的 SOCKS5**。

当解析结果为 `socks5`/`socks5h` + 账号时：

1. HTTP 业务会话：curl_cffi **直连上游 socks5h**（你的住宅节点）。
2. 本地 Headless：启动 **本机 HTTP 桥**（`paypal/proxy_bridge.py`），把浏览器流量转发到同一上游 SOCKS。

桥仅监听 `127.0.0.1:随机端口`，不改变上游节点。

安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-headless.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

## 6. 会话层与探测 CA（`session.py` / `ssl_env.py` / `probe_proxy_entry`）

- `trust_env=False`：不吃环境变量里的陌生代理。
- 显式设置 `proxies`：避免关闭填写代理后仍被劫持。
- 任务运行期会 scrub 进程内 `HTTP_PROXY` 等，减少双层代理。
- **代理 HTTPS 探测**与业务会话一样使用 `ensure_ssl_cert_env()` 的 ASCII CA  
  （`C:\ProgramData\PP-TH\cacert.pem`），避免中文用户路径 curl **77**。

## 7. Web「测试代理」

`POST /api/proxy/test` 与任务使用同一套 `resolve_outbound_proxy`。

成功返回字段包括：`exit_ip`、`resolved_scheme`、`resolve_note`、`latency_ms`。

## 8. 常见故障对照

| 现象 | 真实含义 | 处理 |
|------|----------|------|
| 秒失败「代理拒绝 IP」但正文无 `forbidden ip=` | 旧版误分类；现已修 | 更新后看原文：多半是 TLS/节点挂 |
| curl **35** / SSL handshake 被关 | 半开 Clash 或住宅节点不通 | 关代理直连冒烟；或开 **TUN**；或换节点 |
| curl **77** / trust anchors | 中文路径 CA | 已自动镜像；仍失败则重启 Web |
| 真 `forbidden ip=x.x.x.x not supported` | 代理商拒当前公网 IP | 加白或开 TUN 改出口 |
| 端口 7897 通但任务失败 | 端口在听 ≠ HTTPS 出网 | 开 TUN 或关系统代理用 direct |

## 9. 推荐用法

### A. 与巴西项目一致（最稳）

1. 客户端开 **TUN / 虚拟网卡**
2. Web **代理框清空、代理开关关**
3. 选协议国家后开跑

### B. 关 TUN，只用填写的住宅代理

1. 代理商后台把**当前公网 IP** 加入白名单
2. 填写 `socks5h://user-region-XX:pass@host:port`（或 `http://`，由程序自动尝试 socks5h）
3. 先点「测试代理」，确认出口国家与协议国家尽量一致
4. 再「开始执行」

### C. 本机直连冒烟（假 BA）

1. 关代理开关  
2. 假 BA 如 `BA-ABCDEFGH12345678`  
3. 期望 Phase0/1/2 后 `INVALID_TOKEN` —— **引擎可跑**

### D. 系统代理（仅开系统代理、未开 TUN）

仅当本机混合端口**自身已能 HTTPS 出网**时可用。端口在线但 TLS 失败 = 客户端没真正出网；默认 **不会** 为了「未填代理」去硬探它。

## 10. 相关代码

| 文件 | 作用 |
|------|------|
| `paypal/proxy.py` | 解析、探测（带 CA）、系统代理、forbidden IP 诊断、`resolve_outbound_proxy` |
| `paypal/ssl_env.py` | ASCII CA 镜像（会话 + 探测共用） |
| `paypal/proxy_bridge.py` | SOCKS 认证转本地 HTTP 桥（Playwright，CLI 高级） |
| `paypal/session.py` | curl_cffi/httpx 出网注入 |
| `web.py` | `require_proxy=bool(filled_raw)`、测试代理 API、`classify_proxy_transport_error` |

## 11. 安全

- `.env`、真实代理账号、API Key **禁止提交**
- 日志中密码打码为 `***`
- 见 `SANITIZATION.md`