# 环境安装与启动

> 更新：2026-08-10 · 与当前 `main` 代码一致

## 1. 基础依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt`：`curl_cffi`（会话首选）、`httpx`、`faker`、`unidecode`、`loguru` 等。

## 2. Headless（可选，非必须）

仅当你要在 Web/CLI 里选 **Headless** 风控引擎时需要：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-headless.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

纯协议路径（`random` + `protocol` + `python_generated`）**不需要** Playwright。  
CentOS 7 等老系统若装 headless，见 [HANDOFF.md](./HANDOFF.md) §7（常需固定 `playwright==1.30.0`）。

## 3. 配置

```powershell
copy .env.example .env
```

| 变量 | 含义 |
|------|------|
| `PAYPAL_PROXY_URL` / `PAYPAL_PROXY_POOL` | 默认代理（Web 填写优先） |
| `PAYPAL_USE_SYSTEM_PROXY` | `1` 时允许回退本机 Clash 等 |
| `PAYPAL_ROXY_API_KEY` / HOST / PORT | Roxy Local API |
| `SMSBOWER_API_KEY` 等 | 自动接码（可选） |
| `PAYPAL_FINGERPRINT_SOURCE` | `random` / `headless` / `roxy` / … |
| `PAYPAL_DATADOME_MODE` | `protocol` / `headless` / `roxy` / … |
| `PAYPAL_MTR_RUNTIME` | `python_generated` / `headless` / `roxy` / … |
| `PAYPAL_RUNTIME_MODE` | `protocol` / `headless` / `auto` / `roxy` |
| `PAYPAL_ONLINE_ADDRESS` | `1`（默认）OSM 在线地址；`0` 仅本地池 |
| `PAYPAL_CONTINUE_MERCHANT` | `1` 开启 A 后 B/C（默认 `0`） |
| `PAYPAL_WEB_*` | 任务上限、OTP 超时、生产模式等 |

**优先级**：Web/CLI 字段 > 环境变量 > `config.py`  
完整模板：`.env.example`。

## 4. 启动 Web

```powershell
.\start.bat
# 或
.\.venv\Scripts\python.exe web.py --host 127.0.0.1 --port 8080
```

打开：http://127.0.0.1:8080

### Web 表单当前能力

- **国家**：44 国可搜索下拉
- **Buyer 身份**：`原版流程` / `注册后升 Guest、绑 EC 再授权`（`elevate_bind`）
- **指纹 / DataDome / MTR**：可选 Headless、纯协议或 Roxy（**不是**锁死只读）
- **代理**：填写 +「测试代理」
- **地址**：任务内自动 `OSM → ADDRESS_POOLS`
- **OTP**：面板交互；可选 SMSBower

### API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/regions` | 国家列表 |
| GET | `/api/runtime` | 推荐默认 + 枚举（含 buyer 模式） |
| POST | `/api/proxy/test` | 测代理 |
| POST | `/api/jobs` | 建任务（`buyer_identity_mode` 等） |
| GET | `/api/jobs/{id}` | 详情与日志 |
| POST | `/api/jobs/{id}/otp` | OTP / 换号 |

建任务时 **手机国际区号必须与 `country` 一致**，否则 400。  
任务列表按 Cookie `paypal_web_device_id` 隔离。

## 5. CLI 示例

```powershell
# 纯协议 + 升权
.\.venv\Scripts\python.exe main.py --country BR --ba-token BA-xxx --phone +5511... --buyer-mode elevate_bind --runtime protocol

# 带代理
.\.venv\Scripts\python.exe main.py --country NL --ba-token BA-xxx --phone +316... --proxy-url "socks5h://user:pass@host:port"
```

## 6. 代理详解

见 [PROXY.md](./PROXY.md)。

## 7. Roxy（可选）

1. 本机启动 RoxyBrowser Local API  
2. Web 面板或环境变量填 API Key  
3. 指纹/DataDome/MTR 选 `roxy`  
4. 未填代理时窗口走本机网络

## 8. 测试

```powershell
$env:PAYPAL_ONLINE_ADDRESS = "0"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 9. 故障速查

| 现象 | 处理 |
|------|------|
| `playwright is not installed` | 装 headless 依赖，或表单改纯协议三项 |
| SOCKS5 认证 + Chromium | [PROXY.md](./PROXY.md) 本地 HTTP 桥 |
| `forbidden ip not supported` | 白名单 / TUN / 系统代理 |
| `curl 97` | 上游 HTTP 403，见 PROXY |
| `curl 77`（Windows） | 确认 `ssl_env` CA 镜像到 ASCII 路径 |
| 创建任务 400 phone/country | 区号与国家一致（BR=`+55`，勿混 `+66`） |
| OSM 拖慢 | `PAYPAL_ONLINE_ADDRESS=0` |
| 假 BA Phase2 无 EC | 预期失败；换真实 BA |
| 任务列表空 / 详情 404 | 带上 device cookie；勿裸 curl 查他人任务 |
| 升权未生效 | `buyer_identity_mode=elevate_bind`，日志含 elevate / Buyer |

协议链路：[PROTOCOL_CHAIN.md](./PROTOCOL_CHAIN.md) · 总览：[README.md](./README.md) · 交接：[HANDOFF.md](./HANDOFF.md)
