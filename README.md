# PP Multi · PayPal 多国 Billing Agreement 纯 HTTP 全协议

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-private-lightgrey)](#)

本地可运行的 **多国 PayPal Billing Agreement** 实现：以纯 HTTP 状态机为主，可选本地 Headless / Roxy 风控辅助；**不依赖**远端 job 平台。

仓库：https://github.com/suixin00001111/PP-TH-

| 文档 | 用途 |
|------|------|
| **[AI_HANDOFF.md](./AI_HANDOFF.md)** | 给后续 AI / 协作者的完整交接（必读） |
| [PROTOCOL_CHAIN.md](./PROTOCOL_CHAIN.md) | Phase 0–4 协议链路 |
| [PROXY.md](./PROXY.md) | 代理 / TUN / cliproxy |
| [SETUP.md](./SETUP.md) | 安装与启动细节 |
| [SANITIZATION.md](./SANITIZATION.md) | 脱敏与密钥策略 |

---

## 当前默认（2026-08）

| 项 | 默认 |
|----|------|
| 运行时 | **protocol**（纯 HTTP） |
| 指纹 / DataDome / MTR | `random` / `protocol` / `python_generated` |
| 阶段顺序 | **Phase0 → Phase1（风控信标）→ Phase2 → Phase3 → Phase4**（对齐巴西公开包顺序） |
| ModXO action id | **优先从 HTML/JS 动态提取**；`PAYPAL_MODXO_STATIC_ACTION_IDS=0` |
| 代理 | 未填写时 **允许直连**；不强制半坏 Clash「系统代理」 |
| Web A 层 | 仅 BA；Merchant B/C 默认关 |
| Windows 中文路径 | `paypal/ssl_env.py` 镜像 CA，避免 curl_cffi **error 77** |

假 BA（如 `BA-ABCDEFGH12345678`）用于冒烟：应看到 Phase0 页面 200、Phase1 信标、Phase2 打到 PayPal，然后因 **INVALID_TOKEN / 无 EC / authchallenge** 失败——这是 **预期**，不是“项目起不来”。

**完整成功（OTP / 授权）需要**：真实未过期 BA + 目标国住宅代理（或可用 TUN）+ 手机号 / OTP。

---

## 核心概念（务必分清）

| 概念 | 含义 |
|------|------|
| **泰国 TH** | **流程参考**：状态机以泰国实现为蓝本 |
| **各国协议** | 选中国家后绑定该国 `ProtocolContext`（locale / 区号 / 证件 / 地址） |
| **生成资料** | 姓名 / 城市 / 街道 / 邮编 / 手机区号 **必须对应该国** |
| **巴西公开包** | 本地对照实现（Phase 顺序 / 动态 ModXO）；**不是**本仓库依赖，也不是 pay.153 源码 |

任务启动日志示例：

```text
Protocol context: JP (日本) lang=ja locale=ja_JP phone_cc=+81
--- Phase 0: Initial page load ---
--- Phase 1: Risk control signals ---
--- Phase 2: Create account flow ---
```

---

## 支持的国家（40+）

Web 下拉与 `GET /api/regions` 一致，包括：

`TH JP US GB BR MX ID MY SG PH VN KR HK TW CN AU NZ CA DE FR ES IT NL SE PL PT IE CH AT BE DK NO FI IN AE SA IL TR RU ZA AR CL CO PE`

各国差异：语言/locale、国际区号、分析时区、地址样式；**仅巴西 BR** 生成并提交 **CPF**，其余不强制证件。

---

## 资料生成

- [Faker](https://github.com/joke2k/faker) 按国家 locale 生成姓名/城市/街道
- [Unidecode](https://pypi.org/project/Unidecode/) 转写非拉丁脚本
- `address.country` 与所选协议国家强制一致
- 手机号输入框 placeholder 仅为示例

---

## 功能概览

**A 层（PayPal BA）**：Phase0 协议页 → Phase1 指纹/Tealeaf/analytics → Phase2 ModXO/EC → Phase3 OTP → Phase4 授权

**B/C 层**（可选，默认关）：pm-redirects / SetupIntent / checkout-verify

**控制台**：国家下拉、代理填写与测试、OTP 交互、任务日志、CLI

---

## 快速开始

```bash
git clone https://github.com/suixin00001111/PP-TH-.git
cd PP-TH-
python -m venv .venv
```

Windows（推荐）：

```powershell
.\start.bat
# 自动：venv / pip / .env.example→.env / SSL CA 预检 / web 8080
```

或手动：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe web.py --host 127.0.0.1 --port 8080
```

打开：http://127.0.0.1:8080

核心依赖：`curl_cffi`、`httpx[http2]`、`loguru`、`requests`、`faker`、`unidecode`、`certifi`。

### 代理（重要）

推荐在 **Web 填写** 并先点「测试代理」。

- 支持 `http://` / `socks5://` / `socks5h://` 以及 `host:port:user:pass`
- 住宅节点常会自动升为 **`socks5h`**
- **未开代理**时走直连，不因本机 Clash 半开而硬失败
- 可选：`PAYPAL_USE_SYSTEM_PROXY=1` 才主动用系统/本地客户端代理
- cliproxy `forbidden ip` / TUN：**详见 [PROXY.md](./PROXY.md)**

不要把真实代理账号提交到 Git。也可用 `PAYPAL_PROXY_URL` / `PAYPAL_PROXY_POOL`。

### CLI

```powershell
.\.venv\Scripts\python.exe main.py --country JP --ba-token BA-xxx --phone +819012345678 --proxy
```

| 参数 | 说明 |
|------|------|
| `--ba-token` | BA token（必填，格式 `BA-` + 8–80 位字母数字） |
| `--phone` | 带国际区号手机号（必填；SMSBower 开启时可留空） |
| `--country` | 协议国家，默认 `TH` |
| `--proxy` / `--no-proxy` | 开/关代理 |
| `--debug` | 调试日志 |
| `--max-card-attempts` | 绑卡重试次数 |

---

## Web API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/regions` | 国家列表 |
| GET | `/api/runtime` | 默认运行时 knobs |
| GET | `/api/jobs` | 任务列表（按 device cookie） |
| POST | `/api/jobs` | 创建任务 |
| GET | `/api/jobs/{id}` | 任务详情 + 日志 |
| POST | `/api/jobs/{id}/otp` | 提交 OTP |
| POST | `/api/proxy/test` | 测试代理 |
| POST | `/api/roxy/test` | 测试 Roxy Local API |

创建任务示例：

```json
{
  "ba_token": "BA-xxxxxxxxxxxxxxxxx",
  "phone": "+819012345678",
  "country": "JP",
  "proxy_enabled": true,
  "proxy": "host:port:username:password",
  "runtime_mode": "protocol",
  "fingerprint_source": "random",
  "datadome_mode": "protocol",
  "mtr_runtime": "python_generated",
  "max_card_attempts": 5
}
```

任务归属依赖 Cookie **`paypal_web_device_id`**（首页与 JSON API 会下发）。裸 HTTP 客户端请带 cookie jar。

---

## 项目结构

```text
PP-TH-/
├── config.py / main.py / web.py / start.bat / start.sh
├── .env.example                 # 复制为 .env（勿提交 .env）
├── requirements.txt
├── paypal/
│   ├── flow.py                  # BA 状态机 Phase0–4
│   ├── ssl_env.py               # Windows 非 ASCII 路径 CA 镜像
│   ├── protocol.py / regions.py / oaipy_data.py
│   ├── session.py / proxy.py    # curl_cffi + 代理解析
│   ├── fingerprint.py / tealeaf.py / analytics.py / graphql.py
│   ├── local_headless.py / roxy_fingerprint.py / smsbower.py
│   └── merchant_complete.py / b_layer_handoff.py
├── web_static/                  # 控制台 UI
├── tests/
├── AI_HANDOFF.md / PROTOCOL_CHAIN.md / PROXY.md / SETUP.md
└── README.md
```

---

## 代理格式

```text
host:port:username:password
user:pass@host:port
host:port
http://user:pass@host:port
socks5://user:pass@host:port
socks5h://user:pass@host:port
```

不要写 `http://host:port:user:pass`。完整行为见 **[PROXY.md](./PROXY.md)**。

---

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
# 或
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

冒烟期望：

| 输入 | 期望 |
|------|------|
| 假 BA + 无代理 | Phase0 200 → Phase1 信标 → Phase2 打到 PayPal → 失败（INVALID_TOKEN / 无 EC / authchallenge） |
| 真 BA + 住宅代理 + 手机 | 可能进 Phase3 OTP，Web 输入验证码 |

---

## 常见问题

**每个国家是自己的协议吗？**  
是。流程架子参考泰国；locale/区号/资料/证件按所选国家绑定。

**资料会串成泰国吗？**  
不会。`address.country` 与手机区号强制等于所选国。

**Windows curl 77 / CA 错误？**  
用户目录含中文时 libcurl 读 certifi 失败。`ssl_env` 会把 CA 镜像到 `C:\ProgramData\PP-TH\cacert.pem`。`start.bat` / `web.py` / `main.py` 启动时会执行。

**代理 403 / forbidden ip？**  
多为代理商拒绝当前公网 IP；加白或开 TUN。见 [PROXY.md](./PROXY.md)。

**未填代理却很慢 / 失败？**  
旧逻辑会探测坏系统代理。当前：`PAYPAL_USE_SYSTEM_PROXY=0`（默认）时未填代理直接直连。

**假 BA 失败正常吗？**  
正常。PayPal 会返回 `INVALID_TOKEN` 或 authchallenge；说明协议链路已通。

**任务创建了但详情 404？**  
浏览器需带 `paypal_web_device_id` cookie；API 调试请用 cookie jar。

---

## 边界

- 不能保证自动过 DataDome / hCaptcha（默认 manual/official）
- 动态状态不可死 HAR 硬编码；ModXO id 优先在线扫描
- 仅供授权研究；仓库不含真实密钥（见 `SANITIZATION.md`）

---

## 浏览器运行时与接码

| 能力 | 说明 |
|------|------|
| **protocol** | 纯 HTTP（**默认**，推荐先跑通） |
| **headless** | Playwright 无头辅助 Phase0/1 |
| **auto** | 有 Roxy Key 优先 Roxy，否则 headless |
| **Roxy** | RoxyBrowser Local API（本机 + API Key） |
| **MTR** | `python_generated` / headless / roxy |
| **SMSBower** | 自动接码（默认关），与 Web 手填 OTP 并存 |

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-headless.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

---

## 许可证

私有仓库。

Web 表单可选运行时与 SMSBower；CLI：

```powershell
.\.venv\Scripts\python.exe main.py --country JP --ba-token BA-xxx --phone +81... --runtime headless
.\.venv\Scripts\python.exe main.py --country BR --ba-token BA-xxx --smsbower --smsbower-api-key KEY
```


---

## SMSBower 国家 ID

平台使用数字 `country` 参数。项目内置 ISO2 → ID 映射表：`paypal/smsbower_countries.py`（兼容常见 sms-activate 编号，`BR=73`、`TH=52`、`JP=182`、`US=12` 等）。

覆盖方式：

```text
SMSBOWER_COUNTRY=73
# 或
SMSBOWER_COUNTRY_MAP_JSON={"JP":"182","TH":"52"}
```

## DataDome Phase0（浏览器加深）

当运行时为 `headless` / `auto` / `roxy` 时，Phase0 遇到 403/DataDome/authchallenge 会：

1. 用对应国家 browser profile 调用 Playwright 或 Roxy 解链  
2. 回灌 cookies / datadome / clientid 到 HTTP 会话  
3. 重试协议页加载；仍失败再按重试策略回退  

纯 `protocol` 模式不启浏览器（与默认一致）。

---

## 浏览器运行时安装与使用

### Playwright Headless

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-headless.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

验证（应打印 Chromium 版本）：

```powershell
.\.venv\Scripts\python.exe -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); print(b.version); b.close(); p.stop()"
```

### RoxyBrowser（可选，需本机客户端）

1. 安装并启动 RoxyBrowser，开启 Local API（默认端口常为 50000）  
2. 配置环境变量（勿提交密钥）：

```powershell
$env:PAYPAL_ROXY_API_KEY = "your_key"
$env:PAYPAL_ROXY_API_HOST = "127.0.0.1"
$env:PAYPAL_ROXY_API_PORT = "50000"
$env:PAYPAL_RUNTIME_MODE = "auto"
```

### 运行时选择

| 模式 | 行为 |
|------|------|
| `protocol` | 纯 HTTP（默认） |
| `headless` | Playwright 无头辅助 Phase0/1 |
| `auto` | 有 Roxy Key 优先 Roxy，否则 headless，失败回退 protocol |

Web 表单「运行时」下拉；CLI：`--runtime protocol|headless|auto`

```powershell
.\.venv\Scripts\python.exe main.py --country JP --ba-token BA-xxx --phone +81... --runtime headless
```

### SMSBower（可选，与手填 OTP 并存）

```powershell
$env:SMSBOWER_API_KEY = "your_key"
.\.venv\Scripts\python.exe main.py --country BR --ba-token BA-xxx --smsbower --smsbower-api-key your_key
```

国家数字 ID 见 `paypal/smsbower_countries.py`。详见 `SETUP.md`。

---

## 当前 Web 默认（修订摘要）

| 项 | 默认 |
|----|------|
| 指纹 / DataDome / MTR | **本地 Headless**（需 Playwright Chromium） |
| 业务层 | **仅 A 层实跑**（无 B/C 开关） |
| 代理 | 填写优先；自动 socks5h；系统代理可回退 |
| 文档 | [SETUP.md](./SETUP.md) · [PROXY.md](./PROXY.md) |

变更涉及：`web.py`、`paypal/proxy.py`、`paypal/proxy_bridge.py`、`paypal/session.py`、`paypal/local_headless.py`。
