# PP-TH · PayPal 泰国（TH）Billing Agreement 纯 HTTP 全协议

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-private-lightgrey)](#)

本地可运行的 **泰国（TH）PayPal Billing Agreement** 全协议实现：纯 HTTP 状态机，不依赖远端 job 平台，也不依赖浏览器自动化。

仓库地址：https://github.com/suixin00001111/PP-TH-

---

## 功能概览

- **A 层（PayPal BA）**
  - Phase 0：协议页加载 / DataDome 检测
  - Phase 1：设备指纹 + Tealeaf + analytics
  - Phase 2：ModXO 建账号 → EC / signup
  - Phase 3：Initiate2FA → OTP → SignUpNewMember
  - Phase 4：AuthorizeBilling → `return_url`
- **B/C 层（商户链）**  
  `pm-redirects` / `pay.openai` → SetupIntent → `checkout/verify` → ChatGPT 状态确认
- **本地 Web 控制台**：创建任务、OTP 交互、日志查看
- **CLI 一键跑流程**
- **泰国资料模板**：`+66` 手机、泰文/罗马姓名、曼谷等地址；不提交 CPF

```text
BA approve
  → Phase 0 协议页 / DataDome
  → Phase 1 指纹 + Tealeaf + analytics
  → Phase 2 ModXO create-account → EC / signup
  → Phase 3 2FA / OTP / 注册
  → Phase 4 授权 → return_url
  → 商户链 B/C
```

---

## 环境要求

- Windows / Linux / macOS
- Python **3.10+**（开发机验证过 3.14）
- 可用的 **TH 家宽出口代理**（强烈建议）
- 合法测试用的 `BA-token` 与可收短信的泰国手机号（完整跑通时）

---

## 快速开始

### 1. 克隆

```bash
git clone https://github.com/suixin00001111/PP-TH-.git
cd PP-TH-
```

### 2. 安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Linux / macOS：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置代理（必做）

**不要把真实代理账号写进 Git。** 推荐环境变量：

```powershell
$env:PAYPAL_PROXY_ENABLED = "1"
$env:PAYPAL_USE_SYSTEM_PROXY = "0"
$env:PAYPAL_PROXY_POOL = "host:port:username:password"
```

也支持标准 URL：

```text
http://username:password@host:port
```

或在 `config.py` 的 `PROXY_POOL` 中本地填写（仅本机，勿提交）。

> 说明：`USE_SYSTEM_PROXY=True` 会走本机系统代理（如 Clash `127.0.0.1:7897`）。  
> **要走家宽请保持 `False`，并配置 `PROXY_POOL` / 环境变量。**

可选：

```powershell
$env:STRIPE_PUBLISHABLE_KEY = "pk_live_xxx"   # 商户链 SetupIntent 查询
```

### 4. 启动 Web 界面

Windows：

```powershell
.\start.bat
# 或
.\.venv\Scripts\python.exe web.py --host 127.0.0.1 --port 8080
```

Linux / macOS：

```bash
./start.sh
# 或
python3 web.py --host 127.0.0.1 --port 8080
```

浏览器打开：**http://127.0.0.1:8080**

### 5. CLI 运行

```powershell
.\.venv\Scripts\python.exe main.py `
  --ba-token BA-xxxxxxxxxxxxxxxxx `
  --phone +66812345678 `
  --proxy
```

常用参数：

| 参数 | 说明 |
|------|------|
| `--ba-token` | Billing Agreement token（必填） |
| `--phone` | 泰国手机号，如 `+668xxxxxxxx`（必填） |
| `--proxy` / `--no-proxy` | 强制开/关代理 |
| `--proxy-index` | 代理池下标 |
| `--debug` | 调试日志 |
| `--max-card-attempts` | 绑卡失败重试次数 |

---

## Web API（简要）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/jobs` | 当前设备任务列表 |
| POST | `/api/jobs` | 创建任务 |
| GET | `/api/jobs/{id}` | 任务详情 / 日志 |
| POST | `/api/jobs/{id}/otp` | 提交 OTP / 交互输入 |

创建任务 JSON 示例：

```json
{
  "ba_token": "BA-xxxxxxxxxxxxxxxxx",
  "phone": "+66812345678",
  "proxy_enabled": true,
  "max_card_attempts": 5,
  "debug": false
}
```

> 任务按浏览器设备 cookie 隔离，跨浏览器看不到对方任务。

---

## 项目结构

```text
PP-TH-/
├── config.py              # 全局配置（代理请用环境变量）
├── main.py                # CLI 入口
├── web.py                 # Web UI / API
├── start.bat / start.sh   # 一键启动
├── requirements.txt
├── paypal/                # 协议核心
│   ├── flow.py            # 状态机主流程
│   ├── session.py         # curl_cffi 会话
│   ├── proxy.py           # 代理解析（多种格式）
│   ├── fingerprint.py / tealeaf.py / graphql.py
│   ├── merchant_complete.py / b_layer_handoff.py
│   └── oaipy_data.py      # TH 资料 / 卡 / 地址生成
├── web_static/            # 前端静态资源
├── tests/                 # 单元测试
├── PROTOCOL_CHAIN.md      # 协议链路说明
├── REVERSE_NOTES.md       # 逆向笔记
└── SANITIZATION.md        # 脱敏约定
```

---

## 代理格式支持

`paypal/proxy.py` 支持：

```text
host:port:username:password
username:password@host:port
host:port@username:password
host:port                          # 无认证（如本地 mixed）
http://user:pass@host:port
socks5://user:pass@host:port
```

注意：`http://host:port:user:pass` **不是**合法 URL，请勿这样写。

---

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q paypal tests web.py main.py
```

---

## 边界与声明

- 纯 HTTP **不能**自动过 DataDome / hCaptcha；命中验证码会明确失败，不会拉起浏览器。
- ModXO `Next-Action`、EC、signup terms 均为动态状态，不能用死 HAR 常量硬编码。
- 离线单测只验证状态机与校验逻辑，**不保证** PayPal 线上长期接受。
- 本仓库不包含真实 BA、手机、代理账号、Cookie、HAR（见 `SANITIZATION.md`）。
- 仅供授权环境的安全研究 / 协议分析使用，请遵守当地法律与平台条款。

---

## 与巴西包差异（摘要）

| 点 | BR | TH（本仓库） |
|----|----|--------------|
| 手机 | `+55` | `+66` 九位（6/8/9 开头） |
| 语言 | `pt-BR` | `th-TH` |
| 国家码 | `BR` | `TH` |
| 证件 | CPF 必填 | 不送 CPF |
| 资料 | 巴西姓名/CEP | 泰国姓名/地址/邮编 |
| 时区 beacon | UTC-3 | UTC+7 (`g=420`) |

---

## 常见问题

**Q: 代理 403 `forbidden ip=... not supported`？**  
A: 家宽服务商拒绝了你的接入公网 IP。请在代理后台加白名单，或使用允许当前 IP 的账号。

**Q: 为什么不走 Clash 本地端口？**  
A: 默认关闭系统代理，确保出口是你配置的 **TH 家宽**，而不是本机 VPN 节点。

**Q: 假 BA 能跑通吗？**  
A: Phase 0/1 通常可到；Phase 2 需要真实有效 `BA-token` 才能拿到 EC。

---

## 许可证

私有仓库。未声明开源许可前，请勿二次分发敏感用途的衍生实现。