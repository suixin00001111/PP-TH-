# PP-TH 项目交接文档（Handoff）

> 本文档写给**接手的 AI/工程师**，用于理解项目现状、架构约定、已知问题与待优化方向。
> 最后更新：2026-08-10（补充 §7 服务器部署与运维完整信息）

---

## 1. 项目概览

**PP Multi（仓库名 PP-TH）**：本地可运行的多国 **PayPal Billing Agreement 协议支付**实现。以**纯 HTTP 状态机为主**，可叠加本地 Headless（Playwright）浏览器做风控辅助，不依赖远端 job 平台。

- 仓库：`https://github.com/suixin00001111/PP-TH-`
- 技术栈：Python 3.10+（生产环境 3.11）、httpx/curl_cffi、loguru、Playwright（可选）、自建 Web UI（标准库 http.server）
- 支持国家：**40+**，`GET /api/regions` 返回国家目录
- 核心设计：**"多国协议绑定"**——选中国家后绑定该国的 `ProtocolContext`（locale/区号/证件/地址样式/语言），生成的姓名/城市/街道/邮编/手机区号**必须对应所选国家**

### 核心概念（务必分清）

| 概念 | 含义 |
|------|------|
| 泰国 TH | **流程参考**：Phase 0-4 状态机以泰国实现为蓝本 |
| 各国协议 | 选中国家 → 绑定 `ProtocolContext`（locale/区号/证件/地址样式） |
| 生成资料 | 姓名/城市/街道/邮编/区号必须对应所选国家，不会把泰国资料填进别的国家 |
| 巴西 BR | **风控深度参考**：风控信号/浏览器 runtime 以 openai-paypal（巴西深度版）为蓝本 |

---

## 2. 快速上手

### 本地 / 服务器运行

```bash
# 安装依赖
pip install -r requirements.txt
# 可选 headless 风控
pip install -r requirements-headless.txt && python -m playwright install chromium

# Web UI（推荐，含任务面板/OTP 交互/日志实时流）
python web.py --host 0.0.0.0 --port 8080

# CLI 单跑
python main.py --ba-token BA-xxx --phone +66xxxxxxxxx --country TH \
  --runtime headless --buyer-mode elevate_bind
```

### 环境变量（.env 或环境）

| 变量 | 默认 | 说明 |
|------|------|------|
| `PAYPAL_FINGERPRINT_SOURCE` | random | 指纹来源：random/roxy/headless/auto |
| `PAYPAL_DATADOME_MODE` | protocol | DataDome：protocol/roxy/headless/auto/off |
| `PAYPAL_MTR_RUNTIME` | python_generated | MTR sealedResult：python_generated/roxy/headless/auto/off |
| `PAYPAL_RISK_SIGNALS_MODE` | protocol | signup 前风控：roxy/headless 等（对齐母版后 protocol 归 headless） |
| `PAYPAL_PROXY_ENABLED/URL/POOL` | - | 代理开关/单条/代理池 |
| `PAYPAL_SMSBOWER_API_KEY` | - | 自动接码（可选） |
| `PAYPAL_WEB_OTP_TIMEOUT_SECONDS` | 1800 | Web 等验证码超时 |

---

## 3. 代码库地图

### 根目录
| 文件 | 职责 |
|------|------|
| `main.py` | CLI 入口（--ba-token/--phone/--country/--runtime/--buyer-mode 等） |
| `web.py` | Web UI 服务：任务管理、OTP 交互、日志流、代理/风控测试接口 |
| `config.py` | 全局配置 + 多国画像常量 |
| `requirements*.txt` | 依赖清单（headless 版本见 §7 坑） |
| `SETUP.md` / `README.md` / `PROXY.md` / `SANITIZATION.md` / `PROTOCOL_CHAIN.md` / `REVERSE_NOTES.md` | 部署/说明/代理/脱敏/协议链/逆向笔记 |

### paypal/ 核心模块
| 模块 | 职责 |
|------|------|
| `flow.py` | **核心状态机**（Phase 0-4 + 重试 + elevate_bind 分支）约 8000 行 |
| `protocol.py` | 多国 ProtocolContext（locale/区号/证件/地址样式） |
| `regions.py` / `region_matrix.py` | 国家归一化 / 国家矩阵 |
| `country_profiles.py` / `oaipy_data.py` | 各国资料生成（姓名/地址/证件，TH 专用数据） |
| `proxy.py` / `proxy_bridge.py` | 代理解析/池/诊断 + SOCKS5 认证本地 HTTP 桥 |
| `fingerprint.py` | 程序合成浏览器指纹（random 模式） |
| `roxy_fingerprint.py` | Roxy 浏览器指纹捕获（Local API） |
| `local_headless.py` | Playwright headless 指纹/DataDome/MTR/签名上下文（**已重建为母版版本**，仅加 proxy_bridge 桥） |
| `mtr.py` | MTR dfp.js sealedResult 生成/回灌 |
| `session.py` | HTTP 会话（httpx + curl_cffi + 风控 header 注入） |
| `runtime_config.py` | runtime 模式映射（real/test profile → 各模式默认值） |
| `runtime_bridge.py` | 运行时桥（datadome/风险信号跨模式分发） |
| `smsbower.py` / `smsbower_countries.py` | 自动接码 + 国家映射 |
| `analytics.py` / `tealeaf.py` / `traffic_recorder.py` | 遥测/Tealeaf/流量录制 |
| `graphql.py` | GraphQL 请求构造 |
| `models.py` | 数据模型（UserInfo/CardInfo/BillingAddress/SessionState/WebJob） |
| `merchant_complete.py` / `b_layer_handoff.py` / `layer_status.py` | 商户完成/B 层交接/分层状态 |

### web_static/（Web UI 前端）
| 文件 | 职责 |
|------|------|
| `index.html` | 页面结构（任务表单、OTP 面板、日志、结果面板） |
| `app.js` | 前端逻辑（轮询/渲染/交互） |
| `app.css` | 样式 |

### tests/（16 个测试文件，当前 61 个用例全绿）
覆盖：流程状态守卫、国家画像保真、JP/TH 画像、协议上下文、手机号归一化、session authchallenge、runtime 桥、买家身份模式、代理辅助函数等。

---

## 4. 核心流程（Phase 0-4）

```
Phase 0  Initial page load     加载 agreements/approve，处理 DataDome 403，
                                提取 ctxId/ssrt/ModXO action ids/EC token
Phase 2  Create account flow   ModXO server-action（Pay_With_Card → createAccount），
                                拿到 onboardingRedirectUrl → 提取 EC token
Phase 3  Signup + 2FA          idapps OTP challenge → InitiateRiskBased2FA → 发短信
                                → Confirm（OTP）→ SignUpNewMember（建号+绑卡）
Phase 4  Final authorization   Hagrid/Hermes review → authorize mutation
                                （BUYER_NOT_SET 时重载上下文重试）
```

**Buyer 身份模式（`buyer_identity_mode`）**——Web 下拉/CLI `--buyer-mode`：
- `legacy`（默认/原版）：Phase 4 由 Hagrid 上下文绑定 buyer
- `elevate_bind` / `identity_elevation`（注册后升 Guest、绑 EC 再授权）：
  `_elevate_guest_identity()` → `_bind_buyer_to_current_ec()` → `_phase4_authorize(skip_initial_hagrid=True)`
- 别名映射在 `flow.py _normalize_buyer_identity_mode` 和 `web.py` 各一份（注意同步）

**重试体系**：
- 卡片重试：`_signup_with_card_retry`（max_card_attempts=5，卡被拒换新卡）
- 全流程重试：`run()` 外层（max_flow_attempts），`_should_retry_full_flow_exception`
- 拒号处理：`web.py _confirm_phone_with_retry` → `wait_for_input` 等待用户在 UI 输新号

---

## 5. 风控信号三引擎（对齐母版）

三个维度各自独立，可分别选 engine：**纯协议（默认）/ Roxy / Headless**，`auto` 自动降级。

| 维度 | 默认（纯协议） | Roxy | Headless |
|------|---------------|------|----------|
| 浏览器指纹 `FINGERPRINT_SOURCE` | random：程序合成 UA/canvas/WebGL 模板 | Local API 开指纹窗口读真实信号 | Playwright 读 runtime 信号 |
| DataDome `DATADOME_MODE` | protocol：提取 clientid + 注入 header + 空 token POST | 真实 Chrome 跑 challenge 回灌 cookie | 同 Roxy（本地无头） |
| MTR `MTR_RUNTIME` | python_generated：模板生成 sealedResult POST /mtr/x0 | 加载 dfp.js 监听真实 x0 回灌 | Playwright 执行 dfp.js |

**注意**：对齐母版后，`_signup_context_risk_mode()` 只返回 roxy/headless（protocol 配置也归 headless）——signup 前风控信号**默认走 headless 浏览器**（需 Playwright）。

---

## 6. 与母版 openai-paypal 的关系（关键背景）

- 母版：`openai-paypal`（巴西单国深度版）——**行为基准**
- 本仓库：多国版——**以母版为 A 层参考机，对齐"行为逻辑"，保留"多国化"**

### 已对齐（2026-08-06 完成，勿回退）
1. `build_proxy_config`：enabled=False 显式优先；enabled=None 时 custom 隐式启用；读 .env
2. `load_proxy_pool`：PAYPAL_PROXY_URL > PAYPAL_PROXY_POOL > config.PROXY_POOL，移除系统代理兜底
3. `_signup_context_risk_mode`：只返回 roxy/headless（protocol 归 headless）
4. ModXO 流程：**跟随所有重定向**（无 fail-fast），异常仅 warning 后 fallback legacy POST
5. Phase 0：DataDome challenge 后**继续**（不硬停），协议空 token POST 一次
6. signup payload：crsData=None、不 omit null、DOB 无默认（空返回 {}）、firstName/lastName 直接取
7. token 提取：只认 `accessToken` 键
8. 重试策略：无 non_retry_markers，错误消息母版格式
9. `local_headless.py`：**用母版版本重建**（仅保留 proxy_bridge SOCKS5 认证桥）
10. roxy：https→HTTPS 映射、无 allow_noproxy raise、额度不足直接复用旧窗口
11. `ProxyEntry.url/label`：username **或** password 非空即带认证
12. `resolve_outbound_proxy`：用户填写优先，系统代理仅回退

### 保留的多国化特性（勿删）
- regions/protocol/oaipy_data/country_profiles 资料生成
- identityDocument 按国家（仅 BR 发 CPF）
- 地址格式、手机号归一化、SMSBower 国家映射、config 多国画像
- 显式 protocol 模式的纯 HTTP 路径（PP-TH 核心设计，README 明确）
- proxy_bridge（socks5 auth 本地桥）

### 与母版的剩余差异（均为多国化必需/新增功能，非行为偏离）
- flow.py：多国协议绑定、elevate_bind 分支（母版无）、诊断写 JSON、TH 地址清洗
- proxy.py：多格式解析、diagnose、系统代理读取（新增功能）
- web.py / main.py / config.py：多国配置与 CLI/Web 重构

---

## 7. 服务器部署与运维（CentOS 7 注意）

### 7.1 服务器基础信息

| 项 | 值 |
|----|----|
| IP | `156.238.252.168` |
| 系统 | CentOS Linux 7（内核 3.10.0-957.el7），GLIBC **2.17**（决定很多坑） |
| 配置 | 16 核 / 15G 内存 / 100G 磁盘（约 99G 可用） |
| 登录 | `root` + 密码（SSH 22；密码在用户手里，文档不写明文） |
| 项目位置 | `/opt/pp-th`（61 个文件，2026-08-07 上传） |
| 其他 | 服务器上另有 `/opt/zkky`（用户其他项目，与本项目无关，勿动） |

### 7.2 服务器上部署了什么（2026-08-07 完成）

**Python 运行时**：`/opt/pp-th/.condaenv`（**Python 3.11.13** + pip 26.1.2）
- 安装路径（CentOS 7 专用，照抄即可）：旧版 Miniconda `Miniconda3-py38_4.12.0-Linux-x86_64.sh` → `/opt/miniconda3` → `conda create -p /opt/pp-th/.condaenv python=3.11`
- **为什么不用新版 Miniconda / 系统 python3**：新版 Miniconda 要求 GLIBC≥2.28（系统只有 2.17）；系统 yum 的 python3 是 3.6.8（项目需要 3.10+ 语法）

**Python 依赖**（已装，`/opt/pp-th/.condaenv`）：
- `requirements.txt`：httpx[http2]、loguru、requests、faker、unidecode、pako、curl_cffi
- `requirements-headless.txt`：**playwright==1.30.0**（固定版本，见下）+ greenlet 3.2.5
- 安装坑：greenlet 不能源码编译（gcc 4.8.5 太老），必须 `pip install --only-binary=:all: greenlet` 用预编译 wheel

**Playwright + Chromium**（headless 风控用）：
- Chromium 110（`~/.cache/ms-playwright/`，playwright 1.30 自带版本），headless 启动验证通过（`LAUNCH_OK`）
- **必须固定 playwright==1.30.0**：新版 playwright 的 node driver 需要 GLIBC_2.25/2.28，CentOS 7 跑不了（实测 1.40/1.48 全部报 `GLIBC_2.28 not found`）
- 注意：`requirements-headless.txt` 里写的 `playwright>=1.40.0` 与服务器不符——**重装环境时必须改成 `playwright==1.30.0`**

**系统软件（yum 装的）**：
- 基础：python3(3.6.8，作为 conda 之外的备胎)、git、unzip、curl、gcc、gcc-c++、make
- Chromium 运行依赖：at-spi2-atk、at-spi2-core、libxkbcommon、alsa-lib、pango、cairo、mesa-libgbm、nss 等（缺库时 Chromium 启动会报 `Missing libraries`）

**服务器上已有的 Chrome 125**：`/opt/chrome125/chrome-linux64/chrome`（独立安装的 Chrome 125，**非本项目 playwright 装的**；项目 headless 用的是 playwright 的 Chromium 110）。交接时注意区分，别混淆。

**Web 服务**：web.py 常驻 8080，公网可访问 `http://156.238.252.168:8080`

### 7.3 Web 服务运维命令

```bash
PY=/opt/pp-th/.condaenv/bin/python
cd /opt/pp-th

# 启动（setsid 脱离会话；重启服务器后必须手动重启）
setsid $PY web.py --host 0.0.0.0 --port 8080 </dev/null >>/tmp/ppweb.log 2>&1 &

# 停止（清空所有内存态任务）
pkill -f 'web.py --host 0.0.0.0 --port 8080'

# 重启 = 先停后启（内存任务会丢失，属正常）
# 查看日志
tail -f /tmp/ppweb.log
# 健康检查
curl -s http://127.0.0.1:8080/api/health   # -> {"ok":true,...}
```

### 7.4 已部署的前端修复（勿回退/勿覆盖）
- `web_static/app.js`：加了 `setInterval(() => { if (state.currentJobId) pollCurrent(false); }, 3000)`（3 秒轮询当前任务，等待输入面板自动弹出）
- `web_static/index.html`：静态资源带版本号（`/static/app.js?v=2`、`app.css?v=2`，防浏览器缓存旧 JS）
- **改动前端后记得递增 `?v=2` → `?v=3`**，否则浏览器缓存会导致"改了不生效"

### 7.5 服务器上验证过的状态（2026-08-07）
- 61 个单元测试全部通过（`python -m unittest discover -s tests`）
- `compileall` 全模块通过
- headless Chromium 启动 + 访问 paypal.com 成功
- Web `/api/health` 正常；泰国 BA 任务 Phase 0-2 实机跑通（德国任务卡在 PayPal 拒号，非程序问题，见 §9）

### 7.6 运维注意
- **SSH 链路不稳定**（延迟波动 191-827ms）：用 paramiko 需 `banner_timeout=30` + 重试 5-6 次；直接 ssh 会偶发 `Error reading SSH protocol banner`
- **任务为内存态**：web.py 重启即丢失所有任务；`/api/jobs` 按浏览器 cookie（device_id）隔离，curl 不带 cookie 查不到任务（属正常）
- 本地代理端口 `127.0.0.1:10808`：项目 proxy_bridge 或用户代理在用，headless Chromium 挂它上面属正常

---

## 8. 测试与验证

```bash
python -m unittest discover -s tests   # 当前 61 用例全绿（服务器/本地一致）
python -m compileall -q paypal web.py main.py config.py
```

- 服务器验证过：61 测试通过、compileall 通过、headless 启动 `LAUNCH_OK`（Chromium 110）
- 新功能必须配套测试（对齐母版的测试已同步更新为"验证母版行为"）

---

## 9. 已知问题与风险（重要）

1. **PayPal 拒号 NUMBER_NOT_SUPPORTED**（高频痛点）：
   - 德国 015x 号段、接码平台虚拟号被 PayPal 硬拒（authId/challengeId 为 null，验证码根本没发）
   - 建议：用真实 SIM 号、或换巴西/泰国（容忍度高）、或换干净代理 IP；**不要在同一 IP 连续换号重试**（风控累积）
2. **recaptcha authchallenge**：signup 页可能遇到 reCAPTCHA，当前外部 solver 禁用，仅 warning 继续——走到 SignUpNewMember 时可能被拦（潜在阻塞点）
3. **BA token 单次/短时效**：同一 token 用第二次可能返回 generic-error（ModXO countries 403）
4. **playwright 1.30 限制**：CentOS 7 只能装 1.30.0（Chromium 110），`requirements-headless.txt` 写的 `>=1.40.0` 与服务器不符——**若重装环境需固定 `playwright==1.30.0`**
5. **Web 任务为内存态**：重启 web.py 即丢失所有任务；`/api/jobs` 按浏览器 cookie（device_id）隔离
6. **elevate_bind 实机未完整验证**：单元测试覆盖分支调用链，但需真实号跑通 Phase 3+4 才算全链路验证

---

## 10. 待优化 / 设计方向（参考竞品 PAY.153）

竞品：`https://pay.153.ink/paypal-pay/`（协议支付工作台，功能参考）

| 优先级 | 方向 | 说明 |
|--------|------|------|
| 高 | ① 验证码人工操作面板 | 服务器临时 Chromium + 实时画面流（点击/输入/滚动/Tab/Enter），或粘贴 datadome cookie/adsddtoken 跳过验证——解决 DataDome/hCaptcha 人工验证（API 可参考：`/jobs/{id}/browser/frame` + `/browser/action`） |
| 中 | ② Braintree Vault 生成 BA 链接 | `buyerCountry/locale/vault=true/intent=tokenize/fundingSource=paypal`，从源头生成 BA 授权链接（Grok 订阅场景） |
| 中 | ③ 拒号自动换号策略 | 拒号时自动换候选号/换国家重试（当前是等人工输入） |
| 低 | ④ 代理池 UI + 成功统计面板 | 多行代理粘贴/随机选择/不落盘；今日成功/平均耗时/24h 时间线 |

---

## 11. 工作约定（用户偏好，请遵守）

1. **行为对齐母版**：修改风控/重试/流程逻辑前，先对照母版 `openai-paypal` 的行为；"增强"需用户拍板
2. **多国化不可破坏**：任何改动不能破坏 40+ 国家资料生成的一致性
3. **改代码必须配套测试**：测试套件需保持全绿（61 用例）
4. **CLI/Web/前端参数要同步**：新增模式时同步 flow.py + web.py + index.html/app.js（曾因不同步出 bug）
5. **Web UI 修复注意**：`app.js` 静态资源已加 `?v=2` 版本号防缓存；改前端后记得递增版本号
6. 交互操作：任务等待验证码时走 `wait_for_input`/Web UI 输入，勿在服务器用 stdin
7. 服务器凭据与代理信息属于敏感信息，交接/文档中不要写明文

---

*交接人：WorkBuddy（2026-08-07）。有疑问可查看 `REVERSE_NOTES.md`（协议逆向笔记）与 `PROTOCOL_CHAIN.md`（协议链）。*
