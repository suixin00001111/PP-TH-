# PP Multi · PayPal 多国 Billing Agreement 纯 HTTP 全协议

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-private-lightgrey)](#)

本地可运行的 **多国 PayPal Billing Agreement** 实现：纯 HTTP 状态机，不依赖远端 job 平台，也不依赖浏览器自动化。

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

---

## 功能概览

**A 层（PayPal BA）**：Phase0 协议页 → Phase1 指纹/Tealeaf → Phase2 ModXO/EC → Phase3 OTP → Phase4 授权

**B/C 层**：pm-redirects / pay.openai → SetupIntent → checkout/verify

**控制台**：国家下拉、代理填写与测试、OTP 交互、任务日志、CLI

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

### 代理

推荐在 **Web 填写**（可「测试代理」）。无协议前缀时默认补 `http://`。

不要把真实代理账号提交到 Git。也可用环境变量 `PAYPAL_PROXY_ENABLED` / `PAYPAL_PROXY_POOL` / `PAYPAL_PROXY_URL`。

### CLI

```powershell
.\.venv\Scripts\python.exe main.py --country JP --ba-token BA-xxx --phone +819012345678 --proxy
```

| 参数 | 说明 |
|------|------|
| `--ba-token` | BA token（必填） |
| `--phone` | 带国际区号手机号（必填） |
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
| GET | `/api/jobs` | 任务列表 |
| POST | `/api/jobs` | 创建任务 |
| GET | `/api/jobs/{id}` | 任务详情 |
| POST | `/api/jobs/{id}/otp` | 提交 OTP |
| POST | `/api/proxy/test` | 测试代理 |

创建任务示例：

```json
{
  "ba_token": "BA-xxxxxxxxxxxxxxxxx",
  "phone": "+819012345678",
  "country": "JP",
  "proxy_enabled": true,
  "proxy": "host:port:username:password",
  "max_card_attempts": 5
}
```

---

## 项目结构

```text
PP-TH-/
├── config.py / main.py / web.py / start.bat / start.sh
├── requirements.txt
├── paypal/
│   ├── flow.py          # 状态机 + 各国 ProtocolContext
│   ├── protocol.py      # 国家协议上下文（TH 为参考衍生）
│   ├── regions.py       # 国家档案
│   ├── oaipy_data.py    # Faker 多国资料
│   ├── session.py / proxy.py / fingerprint.py / tealeaf.py
│   ├── analytics.py / graphql.py
│   └── merchant_complete.py / b_layer_handoff.py
├── web_static/
├── tests/
├── PROTOCOL_CHAIN.md / REVERSE_NOTES.md / SANITIZATION.md
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
```

不要写 `http://host:port:user:pass`。

---

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

- 假 BA：Phase 0/1 通常可过；Phase 2 预期因无 EC 失败
- 完整 OTP 需真实 BA + 该国号码（建议该国出口代理）

---

## 常见问题

**每个国家是自己的协议吗？**  是。流程架子参考泰国；locale/区号/资料/证件按所选国家绑定。

**资料会串成泰国吗？**  不会。`address.country` 与手机区号强制等于所选国；资料来自该国 Faker locale。

**代理 403？**  接入 IP 白名单或账号问题；可用 Web「测试代理」。

**假 BA？**  一般只到 Phase 0/1。

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
