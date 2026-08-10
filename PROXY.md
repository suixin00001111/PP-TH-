# 代理说明（PP Multi）

本文说明当前代码的**出网解析逻辑**、与巴西项目的差异、常见故障（cliproxy / TUN / 系统代理）。

## 1. 设计目标

1. **优先使用你在 Web 填写的代理**（主机 / 端口 / 账号 / 密码不变）。
2. **不依赖 TUN 才能识别填写的代理**：对住宅节点自动尝试 `socks5h` / `socks5` / `http`。
3. **对齐巴西日常用法**：若 Windows「系统代理」已开（如 Clash `127.0.0.1:7897`），在填写代理不可用时自动回退本地客户端出口。
4. **明确失败原因**：cliproxy `forbidden ip=x.x.x.x not supported` 会直接中文提示，而不是只报 curl 97/28。

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
| 1 | Windows 系统代理开启 | 先探测本机客户端（如 `127.0.0.1:7897`） |
| 2 | Web/CLI 填写了代理 | 对**同一 host/user/pass** 尝试 `socks5h` → `socks5` → `http` → `https` |
| 3 | 填写失败 | 再回退系统代理（若本地端口可用） |

成功后任务日志会出现类似：

```text
Proxy resolved for job: socks5h://user:***@us.cliproxy.io:3010 exit_ip=213.x.x.x note=filled-auto-socks5h
HTTP outbound proxy: socks5h://user:***@us.cliproxy.io:3010
```

页面任务头示例：

```text
socks5://...@us.cliproxy.io:3010 (auto socks5h from filled-auto-socks5h)
```

含义：**仍是你填的节点**，仅协议自动改为 `socks5h`（DNS 也走代理）。

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

## 6. 会话层保证（`paypal/session.py`）

- `trust_env=False`：不吃环境变量里的陌生代理。
- 显式设置 `proxies`：避免关闭填写代理后仍被劫持。
- 任务运行期会处理进程内 `HTTP_PROXY` 等，减少双层代理。

## 7. Web「测试代理」

`POST /api/proxy/test` 与任务使用同一套 `resolve_outbound_proxy`。

成功返回字段包括：`exit_ip`、`resolved_scheme`、`resolve_note`、`latency_ms`。

## 8. 推荐用法

### A. 与巴西项目一致（最稳）

1. 客户端开 **TUN / 虚拟网卡**
2. Web **代理框可清空**
3. 选协议国家后开跑

### B. 关 TUN，只用填写的住宅代理

1. 代理商后台把**当前公网 IP** 加入白名单
2. 填写 `socks5h://user-region-XX:pass@host:port`（或 `http://`，由程序自动尝试 socks5h）
3. 先点「测试代理」，确认出口国家与协议国家尽量一致
4. 再「开始执行」

### C. 系统代理（仅开系统代理、未开 TUN）

仅当本机混合端口**自身已能 HTTPS 出网**时可用。端口在线但 TLS 失败 = 客户端没真正出网。

## 9. 相关代码

| 文件 | 作用 |
|------|------|
| `paypal/proxy.py` | 解析、探测、系统代理、forbidden IP 诊断、出网解析 |
| `paypal/proxy_bridge.py` | SOCKS 认证转本地 HTTP 桥（Playwright） |
| `paypal/session.py` | curl_cffi/httpx 出网注入 |
| `paypal/local_headless.py` | Headless 与 Playwright 代理配置 |
| `web.py` | 测试代理 API、任务解析与 `proxy_label` |

## 10. 安全

- `.env`、真实代理账号、API Key **禁止提交**
- 日志中密码打码为 `***`
- 见 `SANITIZATION.md`