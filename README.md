# PP Multi · PayPal 多国 Billing Agreement 纯 HTTP 全协议

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-private-lightgrey)](#)

本地可运行的 **多国 PayPal Billing Agreement** 实现：以纯 HTTP 状态机为主，Web 默认可叠加本地 Headless（Playwright）风控辅助；不依赖远端 job 平台。

仓库：https://github.com/suixin00001111/PP-TH-

---

## 核心概念（务必分清）

| 概念 | 含义 |
|------|------|
| **泰国 TH** | **流程参考**：Phase 0–4 状态机以泰国实现为蓝本 |
| **各国协议** | 选中国家后绑定该国 `ProtocolContext`（locale / 区号 / 证件 / 地址样式等） |
| **生成资料** | 姓名 / 城市 / 街道 / 邮编 / 手机区号 **必须对应该国**，不会把泰国资料填进其它国家 |

任务启动日志示例：

```text
Protocol context: JP (日本) lang=ja locale=ja_JP phone_cc=+81
```

---

## 支持的国家（40+）

Web 下拉与 `GET /api/regions` 一致，包括：

`TH JP US GB BR MX ID MY SG PH VN KR HK TW CN AU NZ CA DE FR ES IT NL SE PL PT IE CH AT BE DK NO FI IN AE SA IL TR RU ZA AR CL CO PE`

各国差异：语言/locale、国际区号、分析时区 g=、地址样式；**仅巴西 BR** 生成并提交 **CPF**，其余不强制证件。

---

## 资料生成（开源对接）

- 姓名、城市、街道等通过开源库 [Faker](https://github.com/joke2k/faker)（MIT）按国家 locale 生成（如 `th_TH`、`ja_JP`、`pt_BR`、`de_DE`）
- 非拉丁脚本经 [Unidecode](https://pypi.org/project/Unidecode/) 转写，便于表单字段
- `address.country` 与所选协议国家强制一致
- 手机号输入框 **placeholder 仅为示例**；用户填写后显示完整号码
- **地址优先级**（`generate_address`）：
  1. **在线 OSM**（Nominatim → Overpass，带本地缓存）— 环境变量 `PAYPAL_ONLINE_ADDRESS=1`（默认开启）
  2. **本地 `ADDRESS_POOLS`** — 44 国均有 curated 池（含 MY/PH/NZ/ES/IT/…/PE 等，避免 Faker 垃圾占位）
  3. Faker 兜底（仅无池时）
- 关闭在线地址：`PAYPAL_ONLINE_ADDRESS=0`（离线/CI/弱网冒烟推荐）

---

## 功能概览

**A 层（PayPal BA）**：Phase0 协议页 → Phase1 指纹/Tealeaf → Phase2 ModXO/EC → Phase3 OTP → Phase4 授权

**买家身份模式**（Web 下拉 / CLI `--buyer-mode` / API `buyer_identity_mode`）：

| 值 | 说明 |
|----|------|
| `legacy` | 原版：Phase4 由 Hagrid 上下文绑定 buyer |
| `elevate_bind` | 注册后升 Guest → 绑 EC → 再授权（别名：`identity_elevation` / `elevate` / `v2` 等） |

升权实现：`paypal/elevation_flow.py` → `IdentityElevationPayPalFlow`（Web 走 `WebElevationPayPalFlow`）。

**B/C 层**：pm-redirects / pay.openai → SetupIntent → checkout/verify（默认关）

**控制台**：国家下拉、买家模式、代理填写与测试、OTP 交互、任务日志、CLI

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
.\start.bat
# 或 .\.venv\Scripts\python.exe web.py --host 127.0.0.1 --port 8080
```

打开：http://127.0.0.1:8080

依赖：`httpx[http2]`、`loguru`、`requests`、`faker`、`unidecode`。

### 代理（重要）

推荐在 **Web 填写** 并先点「测试代理」。

- 支持 `http://` / `socks5://` / `socks5h://` 以及 `host:port:user:pass`
- 住宅节点常会自动升为 **`socks5h`**（账号主机不变），见任务头 `(auto socks5h from ...)`
- 系统代理（Clash `127.0.0.1:789x`）可在填写代理失败时回退
- cliproxy `forbidden ip` / 关 TUN 问题：**详见 [PROXY.md](./PROXY.md)**

不要把真实代理账号提交到 Git。也可用 `PAYPAL_PROXY_URL` / `PAYPAL_PROXY_POOL`。

### CLI

```powershell
.\.venv\Scripts\python.exe main.py --country JP --ba-token BA-xxx --phone +819012345678 --proxy
.\.venv\Scripts\python.exe main.py --country BR --ba-token BA-xxx --phone +5511... --buyer-mode elevate_bind --runtime protocol
```

| 参数 | 说明 |
|------|------|
| `--ba-token` | BA token（必填） |
| `--phone` | 带国际区号手机号（必填，区号须匹配 `--country`） |
| `--country` | 协议国家，默认 `TH` |
| `--buyer-mode` | `legacy`（默认）或 `elevate_bind` / `identity_elevation` |
| `--runtime` | `protocol` / `headless` / `auto` / `roxy` |
| `--proxy` / `--no-proxy` | 开/关代理 |
| `--debug` | 调试日志 |
| `--max-card-attempts` | 绑卡重试次数 |

---

## Web API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/regions` | 国家列表 |
| GET | `/api/runtime` | 默认运行时 + 买家模式枚举 |
| GET | `/api/jobs` | 任务列表 |
| POST | `/api/jobs` | 创建任务 |
| GET | `/api/jobs/{id}` | 任务详情 |
| POST | `/api/jobs/{id}/otp` | 提交 OTP |
| POST | `/api/proxy/test` | 测试代理 |

创建任务示例（升权 + 巴西）：

```json
{
  "ba_token": "BA-xxxxxxxxxxxxxxxxx",
  "phone": "+5511987654321",
  "country": "BR",
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

注意：`phone` 的国际区号必须与 `country` 一致，否则创建任务会 **400**。

---

## 项目结构

```text
PP-TH-/
├── config.py / main.py / web.py / start.bat / start.sh
├── requirements.txt
├── paypal/
│   ├── flow.py              # 状态机 + 各国 ProtocolContext
│   ├── elevation_flow.py    # 升权模式 IdentityElevationPayPalFlow
│   ├── online_address.py    # OSM Nominatim/Overpass 在线地址
│   ├── country_profiles.py  # 44 国 ADDRESS_POOLS / 卡 BIN / 电话规则
│   ├── protocol.py          # 国家协议上下文（TH 为参考衍生）
│   ├── regions.py           # 国家档案
│   ├── oaipy_data.py        # Faker + 地址路由（在线→池→兜底）
│   ├── session.py / proxy.py / proxy_bridge.py
│   ├── fingerprint.py / local_headless.py / tealeaf.py
│   ├── analytics.py / graphql.py / mtr.py
│   └── merchant_complete.py / b_layer_handoff.py
├── web_static/
├── tests/
├── PROXY.md / SETUP.md / PROTOCOL_CHAIN.md / HANDOFF.md
├── DEPLOY.md / REVERSE_NOTES.md / SANITIZATION.md
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

不要写 `http://host:port:user:pass`。完整行为（自动 scheme、系统代理回退、TUN/白名单）见 **[PROXY.md](./PROXY.md)**。

---

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
# 弱网/离线冒烟可关在线地址，避免 OSM 超时拖慢
$env:PAYPAL_ONLINE_ADDRESS = "0"
```

关键套件：`test_buyer_identity_mode`、`test_online_address`、`test_country_profiles_fidelity`、`test_web_helpers`、`test_flow_state_guards`、`test_regions_phone`。

- 假 BA：可到 Phase 0→2；**预期**因无 EC / authchallenge / generic-error 失败，**不应卡死**
- 完整 OTP + 升权绑 EC：需**真实有效 BA** + 该国号码 + 可用出口（住宅代理/TUN）
- 冒烟验证过：44 国地址池构造、`elevate_bind` 任务创建、HTTP API 模式映射（见 [HANDOFF.md](./HANDOFF.md)）

---

## 常见问题

**每个国家是自己的协议吗？**  是。流程架子参考泰国；locale/区号/资料/证件按所选国家绑定。

**资料会串成泰国吗？**  不会。`address.country` 与手机区号强制等于所选国；优先 OSM/本地池，再 Faker。

**在线地址一直超时？**  设 `PAYPAL_ONLINE_ADDRESS=0` 只用本地池；或检查能否访问 Nominatim/Overpass。

**代理 403 / curl 97 / forbidden ip？**  多为代理商拒绝当前公网 IP；加白名单或开 TUN。详见 [PROXY.md](./PROXY.md)。

**假 BA？**  一般 Phase 0 可过，Phase 2 无 EC 后失败退出（正常）。

**`buyer_identity_mode` 写什么？**  Web/API 用 `elevate_bind` 或别名 `identity_elevation`；都会归一成 `elevate_bind`。

---

## 边界

- 不能自动过 DataDome / hCaptcha
- 动态状态不可死 HAR 硬编码
- 仅供授权研究；仓库不含真实密钥（见 `SANITIZATION.md`）

---

## 许可证

私有仓库。


---

## 浏览器运行时与接码（参考巴西 openai-paypal）

| 能力 | 说明 |
|------|------|
| **protocol** | 纯 HTTP（默认） |
| **headless** | Playwright 无头 Chromium 辅助 Phase0/1 风控 |
| **auto** | 有 Roxy Key 优先 Roxy，否则 headless，失败回退协议 |
| **Roxy** | RoxyBrowser Local API（需本机 Roxy + API Key） |
| **MTR** | headless/roxy/python_generated 信号（随运行时） |
| **SMSBower** | 自动接码（默认关），与 Web 手填 OTP 并存 |

安装 headless 依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-headless.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

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
