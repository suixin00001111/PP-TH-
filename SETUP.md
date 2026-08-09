# 环境安装与启动

## 1. 基础依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` 含 `curl_cffi`（会话首选）、`httpx`、`certifi`、`faker`、`loguru` 等。

**一键（Windows）**：`.\start.bat`  
会创建 venv（若不存在）、安装依赖、从 `.env.example` 复制 `.env`、预检 SSL CA、启动 Web **8080**。

## 2. Headless（可选）

仅在需要浏览器辅助 DataDome / MTR 时安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-headless.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

默认 **protocol** 纯协议不依赖 Playwright。

## 3. 配置

```powershell
copy .env.example .env
```

常用变量（**勿提交真实密钥**）：

| 变量 | 含义 / 建议 |
|------|-------------|
| `PAYPAL_RUNTIME_MODE` | `protocol`（默认）\| `headless` \| `auto` \| `roxy` |
| `PAYPAL_FINGERPRINT_SOURCE` | 默认 `random` |
| `PAYPAL_DATADOME_MODE` | 默认 `protocol` |
| `PAYPAL_MTR_RUNTIME` | 默认 `python_generated` |
| `PAYPAL_MODXO_STATIC_ACTION_IDS` | **`0` 推荐**：动态提取 ModXO id；`1` 允许静态 capture 回填 |
| `PAYPAL_PROXY_ENABLED` | 默认 `0` |
| `PAYPAL_USE_SYSTEM_PROXY` | 默认 `0`（未填代理时不探测 Clash） |
| `PAYPAL_PROXY_URL` / `PAYPAL_PROXY_POOL` | 默认代理池 |
| `PAYPAL_ROXY_*` | Roxy Local API |
| `SMSBOWER_*` | 自动接码（可选） |
| `PAYPAL_CONTINUE_MERCHANT` | 默认 `0`（Web 强制 A 层 only） |

**优先级**：Web/CLI 字段 > 环境变量 > `config.py`

## 4. 启动 Web

```powershell
.\start.bat
# 或
.\.venv\Scripts\python.exe web.py --host 127.0.0.1 --port 8080
```

打开：http://127.0.0.1:8080

健康检查：`GET http://127.0.0.1:8080/api/health` → `{"ok":true,...}`

### Web 当前默认

- 运行时：**protocol**（纯 HTTP）
- 业务：**实跑 A 层 BA**（无 Merchant B/C 开关）
- 国家：可搜索中文下拉
- 代理：填写 +「测试代理」；未开代理允许直连
- 任务 cookie：`paypal_web_device_id`（首页加载即下发）

### 常用 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/regions` | 国家列表 |
| GET | `/api/runtime` | 默认运行时 |
| POST | `/api/proxy/test` | 测试代理 |
| POST | `/api/jobs` | 创建任务 |
| GET | `/api/jobs/{id}` | 任务详情与日志 |
| POST | `/api/jobs/{id}/otp` | 提交 OTP / 换号 |

## 5. CLI 示例

```powershell
.\.venv\Scripts\python.exe main.py --country NL --ba-token BA-xxx --phone +316... --proxy
```

`main.py` 启动时同样会执行 `ensure_ssl_cert_env()`。

## 6. Windows 中文用户路径（curl 77）

若日志出现：

```text
curl: (77) error adding trust anchors ... C:\Users\<中文>\...\certifi\cacert.pem
```

说明 libcurl 无法加载非 ASCII 路径下的 CA。仓库已通过 `paypal/ssl_env.py` 把 CA 镜像到例如：

`C:\ProgramData\PP-TH\cacert.pem`

并设置 `SSL_CERT_FILE` / `CURL_CA_BUNDLE`。正常日志类似：

```text
HTTP client: curl_cffi (chrome) ca=C:\ProgramData\PP-TH\cacert.pem
```

## 7. 代理详解

见 [PROXY.md](./PROXY.md)。

要点：

- 未填代理 + `require_proxy=false` → **direct**，不硬失败
- 填了代理则必须探测成功，否则中文报错提示
- 系统代理仅在 `PAYPAL_USE_SYSTEM_PROXY=1` 或已填代理回退路径时积极使用

## 8. Roxy（可选）

1. 本机启动 RoxyBrowser Local API  
2. Web Roxy 面板填 API Key，或设 `PAYPAL_ROXY_API_KEY`  
3. 指纹/DataDome/MTR 选 roxy 或 auto  
4. 未填代理时任务可显示「本机网络」

## 9. 冒烟自检

1. `GET /api/health` 200  
2. 浏览器打开首页，创建任务（格式合法的假 BA 即可）  
3. 日志应出现：`Phase 0` → `Phase 1: Risk control` → `Phase 2`  
4. 假 BA 最终失败信息常为 `INVALID_TOKEN` / `generic-error` / `authchallenge` / `no valid EC token`  
5. 单元测试：`python -m pytest tests -q`（约 65+）

## 10. 更多

- 协议阶段：[PROTOCOL_CHAIN.md](./PROTOCOL_CHAIN.md)  
- AI 交接：[AI_HANDOFF.md](./AI_HANDOFF.md)  
- 总览：[README.md](./README.md)
