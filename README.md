# PP Multi · PayPal 多国 Billing Agreement 纯 HTTP 全协议

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-private-lightgrey)](#)

本地可运行的 **多国 PayPal Billing Agreement** 实现：以 **纯 HTTP 状态机（A 层 Phase 0–4）** 为主，可选 Playwright Headless / Roxy 做风控辅助；自带 Web 控制台与 CLI，**不依赖**远端 job 平台。

仓库：https://github.com/suixin00001111/PP-TH-

> **文档同步**：2026-08-10（升权模式 · 在线地址 · 44 国地址池 · Web 风控可选手动切换 · 交流群）

### 交流与协作

部署、代理、升权、国家资料等问题，欢迎进群一起讨论，少走弯路：

| 渠道 | 信息 |
|------|------|
| **QQ 交流群** | **`1098798456`** |

进群建议：说明用途（本机 / VPS）、国家、报错原文或关键日志（**打码 BA / 代理账号 / OTP**）。  
Issue 与群聊互补：能复现的缺陷优先开 Issue；用法与排障更适合群里即时沟通。

---

## 核心概念

| 概念 | 含义 |
|------|------|
| **协议国家** | 选中 ISO 国家后绑定该国 `ProtocolContext`（locale / 区号 / 证件 / 地址样式等） |
| **生成资料** | 姓名 / 城市 / 街道 / 邮编 / 手机区号 **必须对应该国**，不会串用其它国家资料 |
| **证件** | 按国家规则：例如 `BR` 会生成并提交 **CPF**；多数国家不强制证件字段 |

任务启动日志示例：

```text
Protocol context: JP (日本) lang=ja locale=ja_JP phone_cc=+81 runtime=protocol
```

---

## 支持的国家（44）

与 Web 下拉、`GET /api/regions` 一致：

`TH JP US GB BR MX ID MY SG PH VN KR HK TW CN AU NZ CA DE FR ES IT NL SE PL PT IE CH AT BE DK NO FI IN AE SA IL TR RU ZA AR CL CO PE`

- 各国：语言 / locale、国际区号、分析时区、地址样式
- 证件字段按国别规则（如 `BR` 提交 CPF）；其余多数不强制
- 全部 44 国均有本地 **`ADDRESS_POOLS`** curated 地址（表单安全 ASCII）

---

## 资料与地址

1. **在线 OSM**（Nominatim → Overpass + 本地缓存）— `PAYPAL_ONLINE_ADDRESS=1`（默认开）
2. **本地 `ADDRESS_POOLS`** — 44 国池，失败或关闭在线时使用
3. **Faker** — 无池时兜底（MIT）；非拉丁脚本经 Unidecode 转写

关闭在线地址（CI / 弱网 / 冒烟）：

```powershell
$env:PAYPAL_ONLINE_ADDRESS = "0"
```

姓名等仍按该国 Faker locale；`address.country` 与所选国强制一致。

---

## 功能概览

### A 层（PayPal BA）

```text
Phase0 协议页 → Phase1 指纹/Tealeaf/analytics → Phase2 ModXO/EC
  → Phase3 OTP/注册 → Phase4 授权
```

### 买家身份模式（必选其一）

| 值 | 入口 | 行为 |
|----|------|------|
| `legacy` | 默认 | Phase4 由 Hagrid/review 绑定 buyer |
| `elevate_bind` | Web 下拉 / CLI `--buyer-mode` / API | 注册后升 Guest → 绑 EC → 再授权 |

- 别名：`identity_elevation`、`elevate`、`v2`、`guest_bind` 等 → 均归一为 `elevate_bind`
- 实现：`paypal/elevation_flow.py` → `IdentityElevationPayPalFlow`  
  Web 升权任务用 `WebElevationPayPalFlow`

### B/C 层

商户链（pm-redirects / SetupIntent 等）默认 **关**（`PAYPAL_CONTINUE_MERCHANT=0`）。

### 控制台

国家、Buyer 模式、指纹/DataDome/MTR 引擎、代理测试、OTP、任务日志、CLI。

---

## 快速开始

```bash
git clone https://github.com/suixin00001111/PP-TH-.git
cd PP-TH-
python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.\start.bat
# 或 .\.venv\Scripts\python.exe web.py --host 127.0.0.1 --port 8080
```

打开：http://127.0.0.1:8080

核心依赖：`curl_cffi`、`httpx[http2]`、`loguru`、`requests`、`faker`、`unidecode`。  
可选 Headless：`requirements-headless.txt` + `playwright install chromium`。

### 代理（重要）

- 优先在 **Web 填写** 并先点「测试代理」
- 支持 `http://` / `socks5://` / `socks5h://` / `host:port:user:pass`
- 住宅节点常自动升为 **`socks5h`**
- 系统代理（Clash `127.0.0.1:789x`）可在填写失败时回退
- 详解：[PROXY.md](./PROXY.md)

勿把真实代理账号提交到 Git。也可用 `PAYPAL_PROXY_URL` / `PAYPAL_PROXY_POOL`。

### CLI

```powershell
.\.venv\Scripts\python.exe main.py --country JP --ba-token BA-xxx --phone +819012345678 --proxy
.\.venv\Scripts\python.exe main.py --country BR --ba-token BA-xxx --phone +5511... --buyer-mode elevate_bind --runtime protocol
```

| 参数 | 说明 |
|------|------|
| `--ba-token` | BA token（必填） |
| `--phone` | 带国际区号（**区号必须匹配** `--country`） |
| `--country` | 协议国家，默认 `TH` |
| `--buyer-mode` | `legacy` 或 `elevate_bind` / `identity_elevation` |
| `--runtime` | `protocol` / `headless` / `auto` / `roxy` |
| `--proxy` / `--no-proxy` | 开/关代理 |
| `--debug` | 调试日志 |
| `--max-card-attempts` | 绑卡重试 |

---

## Web 运行时与默认值（当前真实行为）

| 项 | 说明 |
|----|------|
| 指纹 / DataDome / MTR | **表单可选**：`random`/`protocol`/`python_generated`（纯协议）或 `headless` / `roxy` |
| 表单 HTML 初始选项 | 三项常默认勾 **Headless**（需本机 Playwright）；可手动改纯协议 |
| `GET /api/runtime` 的 `default` | 文档化推荐纯协议：`random` + `protocol` + `python_generated` |
| `create_job` | **尊重客户端**传入的三项 + `buyer_identity_mode` |
| 服务器 `deploy/install.sh` | `.env` 写入纯协议默认；用户仍可在页面改选 Headless/Roxy |
| Buyer 模式 | `legacy` / `elevate_bind` |
| 业务层 | 仅 A 层（无 B/C 开关） |
| 地址 | OSM 在线优先 → 本地池 |

### 纯协议 vs Headless

| 模式 | 适用 |
|------|------|
| 纯协议 `random` + `protocol` + `python_generated` | 服务器部署、无 Chromium、冒烟与多租户默认 |
| Headless | 本机已装 Playwright，希望 Phase0 DataDome 等用真实浏览器辅助 |
| Roxy | 本机 Roxy Local API + API Key |

CLI 覆盖：`--runtime protocol|headless|auto|roxy` 及细粒度 `--fingerprint-source` 等。

---

## Web API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/regions` | 44 国列表 |
| GET | `/api/runtime` | 默认推荐 + 可选枚举（含 `buyer_identity_modes`） |
| GET | `/api/jobs` | 任务列表（按 device cookie 隔离） |
| POST | `/api/jobs` | 创建任务 |
| GET | `/api/jobs/{id}` | 任务详情 / 日志 |
| POST | `/api/jobs/{id}/otp` | 提交 OTP / 换号 |
| POST | `/api/proxy/test` | 测试代理 |
| POST | `/api/roxy/test` | 测试 Roxy（可选） |

创建任务示例（升权 + 纯协议）：

```json
{
  "ba_token": "BA-xxxxxxxxxxxxxxxxx",
  "phone": "+819012345678",
  "country": "JP",
  "proxy_enabled": true,
  "proxy": "host:port:username:password",
  "buyer_identity_mode": "elevate_bind",
  "fingerprint_source": "random",
  "datadome_mode": "protocol",
  "mtr_runtime": "python_generated",
  "max_card_attempts": 5,
  "max_flow_attempts": 1
}
```

**注意**：`phone` 国际区号必须与 `country` 一致，否则 **400**。

任务归属依赖 Cookie `paypal_web_device_id`；裸 curl 不带 cookie 会看不到任务。

---

## 项目结构

```text
PP-TH-/
├── config.py / main.py / web.py / start.bat / start.sh
├── requirements.txt / requirements-headless.txt
├── .env.example
├── deploy/install.sh          # VPS 一键安装
├── paypal/
│   ├── flow.py                # 状态机 Phase0–4
│   ├── elevation_flow.py      # 升权 IdentityElevationPayPalFlow
│   ├── online_address.py      # OSM 在线地址
│   ├── country_profiles.py    # 44 国 ADDRESS_POOLS / BIN / 电话
│   ├── oaipy_data.py          # 资料入口（在线→池→Faker）
│   ├── protocol.py / regions.py
│   ├── session.py / proxy.py / proxy_bridge.py
│   ├── fingerprint.py / local_headless.py / graphql.py / mtr.py
│   └── merchant_complete.py / b_layer_handoff.py
├── web_static/                # 控制台 UI
├── tests/
├── README.md / SETUP.md / PROXY.md / DEPLOY.md
├── PROTOCOL_CHAIN.md / HANDOFF.md / AI_HANDOFF.md
├── REVERSE_NOTES.md / SANITIZATION.md
```

---

## 测试

```powershell
$env:PAYPAL_ONLINE_ADDRESS = "0"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

关键：`test_buyer_identity_mode`、`test_online_address`、`test_country_profiles_fidelity`、`test_web_helpers`、`test_flow_state_guards`、`test_resolve_outbound_proxy`、`test_ssl_env`。

| 场景 | 预期 |
|------|------|
| 假 BA + 直连 | Phase0（常 200）→ Phase1/2 → 无 EC / authchallenge → **failed，不卡死** |
| 44 国构造 | 资料 + `IdentityElevationPayPalFlow` 均可建 |
| 全链路成功 | **真实 BA** + 该国号 + 可用住宅出口（或 TUN） |

---

## SMSBower（可选）

默认关；与 Web 手填 OTP 并存。ISO2→平台数字 ID：`paypal/smsbower_countries.py`（如 `BR=73`、`TH=52`、`JP=182`）。

```powershell
$env:SMSBOWER_API_KEY = "your_key"
.\.venv\Scripts\python.exe main.py --country BR --ba-token BA-xxx --phone +55... --smsbower
```

---

## 常见问题

**每个国家是自己的协议吗？**  
是。locale / 区号 / 资料 / 证件按所选国绑定，互不串用。

**资料会串国家吗？**  
不会。`address.country` 与手机区号强制等于所选国。

**在线地址超时？**  
`PAYPAL_ONLINE_ADDRESS=0` 或检查 Nominatim/Overpass 可达性。

**代理 403 / curl 97 / forbidden ip？**  
多为代理商拒当前公网 IP；加白名单或开 TUN。见 [PROXY.md](./PROXY.md)。

**Windows curl 77？**  
中文路径 CA 问题；`paypal/ssl_env.py` 会镜像到 ASCII 路径（如 `C:\ProgramData\PP-TH\cacert.pem`）。

**假 BA 失败算坏了吗？**  
不算。假 token 只能验证引擎可跑到 Phase2。

**`buyer_identity_mode` 写什么？**  
`elevate_bind` 或别名 `identity_elevation`。

**服务器部署？**  
见 [DEPLOY.md](./DEPLOY.md)。升级：`git pull` + `bash deploy/install.sh`。

**文档看不懂 / 想一起排障？**  
进 **QQ 交流群 `1098798456`**，用法、代理、升权、各国资料问题都可以在群里沟通。

---

## 文档索引

| 文档 | 用途 |
|------|------|
| [SETUP.md](./SETUP.md) | 安装、环境变量、故障速查 |
| [PROXY.md](./PROXY.md) | 代理解析、cliproxy、TUN、Headless 桥 |
| [DEPLOY.md](./DEPLOY.md) | VPS 一键部署与运维 |
| [PROTOCOL_CHAIN.md](./PROTOCOL_CHAIN.md) | Phase 链路与升权分支 |
| [HANDOFF.md](./HANDOFF.md) | 中文工程交接（含服务器笔记） |
| [AI_HANDOFF.md](./AI_HANDOFF.md) | 英文 Agent 交接（与代码同步） |
| [SANITIZATION.md](./SANITIZATION.md) | 脱敏与密钥策略 |
| [REVERSE_NOTES.md](./REVERSE_NOTES.md) | 历史逆向对照（非现行 API） |

**社区**：QQ 交流群 **`1098798456`**（问题一起沟通，见文首「交流与协作」）。

---

## 边界

- 不能自动过 DataDome / hCaptcha（外部 solver 默认禁用）
- 动态状态不可死 HAR 硬编码
- 仅供授权研究；仓库不含真实密钥

## 许可证

私有仓库。
