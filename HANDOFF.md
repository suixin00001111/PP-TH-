# PP-TH 项目交接文档（Handoff）

> 写给接手的 AI/工程师：现状、架构、风险与约定。  
> 最后更新：2026-08-10  
> **表述原则**：只描述本仓库自身能力与行为。

---

## 1. 项目概览

**PP Multi（仓库名 PP-TH）**：本地可运行的多国 **PayPal Billing Agreement** 实现。以 **纯 HTTP 状态机**为主，可叠加 Headless（Playwright）/ Roxy 做风控辅助；自带 Web 与 CLI，**不依赖**远端 job 平台。

- 仓库：`https://github.com/suixin00001111/PP-TH-`
- 技术栈：Python 3.10+（生产常见 3.11）、httpx/curl_cffi、loguru、Playwright（可选）、标准库 `http.server` Web UI
- 支持国家：**44**（`GET /api/regions` / `list_regions_public()`）
- 核心设计：选中国家后绑定该国 `ProtocolContext`；姓名/城市/街道/邮编/区号**必须对应该国**
- 现行能力：`elevate_bind` 升权、OSM 在线地址、44 国 `ADDRESS_POOLS`；Web 风控三项**可选**

### 核心概念

| 概念 | 含义 |
|------|------|
| 协议国家 | 选中国家 → 绑定该国 `ProtocolContext` |
| 生成资料 | 不得串用其它国家姓名/地址/区号 |
| 证件 | 按国别规则（如 `BR` 提交 CPF）；多数国家不强制 |

---

## 2. 快速上手

```bash
pip install -r requirements.txt
# 可选 headless
pip install -r requirements-headless.txt && python -m playwright install chromium

python web.py --host 0.0.0.0 --port 8080

python main.py --ba-token BA-xxx --phone +81xxxxxxxxx --country JP \
  --runtime protocol --buyer-mode elevate_bind
```

### 环境变量（摘要）

| 变量 | 默认 | 说明 |
|------|------|------|
| `PAYPAL_FINGERPRINT_SOURCE` | random | random / headless / roxy / … |
| `PAYPAL_DATADOME_MODE` | protocol | protocol / headless / roxy / … |
| `PAYPAL_MTR_RUNTIME` | python_generated | python_generated / headless / roxy / … |
| `PAYPAL_RISK_SIGNALS_MODE` | protocol | signup 前风控引擎 |
| `PAYPAL_PROXY_*` | - | 代理开关 / URL / 池 |
| `PAYPAL_ONLINE_ADDRESS` | `1` | `1`=OSM 优先；`0`=仅本地池 |
| `PAYPAL_WEB_OTP_TIMEOUT_SECONDS` | 1800 | Web 等验证码超时 |
| `SMSBOWER_*` / `PAYPAL_ROXY_*` | - | 可选接码 / Roxy |

完整见 `.env.example`、[SETUP.md](./SETUP.md)。

---

## 3. 代码库地图

| 路径 | 职责 |
|------|------|
| `main.py` / `web.py` / `config.py` | CLI、Web、配置 |
| `paypal/flow.py` | 状态机 Phase0–4 + 重试 + elevate 分支 |
| `paypal/elevation_flow.py` | `IdentityElevationPayPalFlow` 升权 |
| `paypal/online_address.py` | OSM 在线地址 + 缓存 |
| `paypal/country_profiles.py` | 44 国 `ADDRESS_POOLS` / BIN / 电话 |
| `paypal/oaipy_data.py` | 资料入口（在线→池→Faker） |
| `paypal/protocol.py` / `regions.py` | 协议上下文 / 国家目录 |
| `paypal/session.py` / `proxy.py` / `proxy_bridge.py` | HTTP、代理、SOCKS 桥 |
| `paypal/graphql.py` | 含 BUYER_* 等查询 |
| `paypal/local_headless.py` / `roxy_fingerprint.py` | 可选浏览器辅助 |
| `web_static/` | 控制台 UI |
| `tests/` | 单测（buyer / online_address / pools / proxy / ssl 等） |
| `deploy/install.sh` | VPS 一键安装 |

---

## 4. 核心流程（Phase 0–4）

```text
Phase0  协议页加载 / DataDome 边缘 / ModXO action ids
Phase1  指纹 + Tealeaf + analytics（在 Phase2 之前）
Phase2  ModXO → EC / signup URL
Phase3  OTP + SignUpNewMember
Phase4  授权
        · legacy：review/Hagrid 绑定 buyer
        · elevate_bind：升 Guest → 绑 EC → authorize
```

**Buyer 模式**：Web / CLI `--buyer-mode` / API `buyer_identity_mode`  
- `legacy`（默认）  
- `elevate_bind`（别名 `identity_elevation` 等）→ `WebElevationPayPalFlow` / `IdentityElevationPayPalFlow`  
别名在 `flow.py` 与 `web.py` 各有归一逻辑，改时需同步。

**地址**：OSM（可关）→ `ADDRESS_POOLS` → Faker。

**重试**：换卡 `max_card_attempts`；全流程 `max_flow_attempts`；拒号可 Web 换号。

---

## 5. 风控三引擎

| 维度 | 纯协议 | Headless | Roxy |
|------|--------|----------|------|
| 指纹 | random 模板 | Playwright | Local API |
| DataDome | protocol | Playwright | Local API |
| MTR | python_generated | Playwright | Local API |

服务器 `install.sh` 常把 `.env` 写成纯协议默认；Web 表单仍可改选。  
`create_job` **尊重客户端**传入的三项（校验合法后），不要擅自锁死。

### 实现约定（勿随意回退）

1. 用户填写代理优先；未填且不 require → **direct**  
2. ModXO 跟随重定向；异常可 warning 后 fallback  
3. Phase0 DataDome 后可继续协议路径  
4. signup：crsData=None、姓名直接取、token 认 `accessToken`  
5. 保留 proxy_bridge、多国资料、elevate、在线地址  

---

## 6. 服务器部署与运维

一键路径见 [DEPLOY.md](./DEPLOY.md)（`deploy/install.sh`，systemd `pp-th`，`:8080`）。

### 手工 CentOS 7 笔记（历史环境，仍可能有效）

| 项 | 值 |
|----|----|
| 示例 IP | `156.238.252.168`（以实际为准） |
| 系统 | CentOS 7，GLIBC 2.17 |
| 项目目录 | `/opt/pp-th` |
| Python | 常见为 conda env `/opt/pp-th/.condaenv`（3.11） |
| 旧 Miniconda | 新版 Miniconda 可能要 GLIBC≥2.28，系统 yum python3 过旧 |

Headless 在 CentOS 7 上常需 **`playwright==1.30.0`**（新 driver 要更高 GLIBC）。  
`requirements-headless.txt` 若写 `>=1.40`，重装时注意与系统匹配。

```bash
# 若未用 systemd，手工示例：
PY=/opt/pp-th/.condaenv/bin/python
cd /opt/pp-th
setsid $PY web.py --host 0.0.0.0 --port 8080 </dev/null >>/tmp/ppweb.log 2>&1 &
```

任务为**内存态**；`/api/jobs` 按 cookie `paypal_web_device_id` 隔离。  
SSH 不稳定时注意 banner 超时与重试。

---

## 7. 测试与验证

```bash
PAYPAL_ONLINE_ADDRESS=0 python -m unittest discover -s tests
python -m compileall -q paypal web.py main.py config.py
```

2026-08-10 本地冒烟（假 BA）：关键单测通过；44 国构造 44/44；`elevate_bind` 到 Phase2 失败收尾不卡死；HTTP `identity_elevation` → `elevate_bind`；**phone 区号须匹配 country**。

---

## 8. 已知问题与风险

1. **NUMBER_NOT_SUPPORTED**：部分号段/虚拟号被拒；换真实 SIM、换出口 IP；避免同 IP 狂换号  
2. **authchallenge / reCAPTCHA**：外部 solver 默认禁用，可能卡在注册  
3. **BA 短时效**：同一 token 复用易 generic-error  
4. **老系统 Playwright 版本**与 GLIBC 限制  
5. **Web 任务内存态**，重启即丢  
6. **elevate_bind 全成功**依赖真实 BA + 该国号 + 可用出口；假 BA 只能验到 Phase2  
7. **OSM 超时**：CI/弱网设 `PAYPAL_ONLINE_ADDRESS=0`  
8. **phone/country 不一致** → 创建任务 400  

---

## 9. 待优化方向（产品）

| 优先级 | 方向 |
|--------|------|
| 高 | 验证码人工操作面板 / cookie 粘贴跳过 |
| 中 | 从商户侧生成 BA 链接、拒号自动换号 |
| 低 | 代理池 UI + 成功率统计 |

---

## 10. 工作约定

1. 改风控/流程前先读现有 `flow.py` / 单测；「增强」需用户拍板  
2. 不得破坏 44 国资料与 `ADDRESS_POOLS` 一致性  
3. 改代码配套测试：`PAYPAL_ONLINE_ADDRESS=0 python -m unittest discover -s tests`  
4. CLI / Web / 前端参数同步（含 buyer 别名）  
5. 静态资源若带 `?v=`，改 UI 后递增  
6. OTP 走 Web `wait_for_input`，勿在服务器 stdin 堵死  
7. 文档与密钥：不写明文代理/密码；说明只写本仓库现行行为 
8. Web 风控为**可选**；服务器 `.env` 仅**默认**纯协议  

---

## 11. 2026-08-10 变更摘要

| 主题 | 内容 |
|------|------|
| Identity elevation | `elevation_flow.py`、BUYER_*、Web 选流 |
| Online address | `online_address.py`、`PAYPAL_ONLINE_ADDRESS` |
| Address pools | 44 国 curated 池 |
| 文档 | 全量 md 与现行行为对齐 |

入口：`README.md` · `SETUP.md` · `PROTOCOL_CHAIN.md` · `PROXY.md` · `DEPLOY.md` · `AI_HANDOFF.md`。
