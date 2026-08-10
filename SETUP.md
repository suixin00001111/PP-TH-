# 环境安装与启动

## 1. 基础依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` 含 `curl_cffi`（会话必需）、`httpx`、`faker` 等。

## 2. Headless（Web 默认推荐）

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-headless.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

## 3. 配置

```powershell
copy .env.example .env
```

常用变量（勿提交真实密钥）：

| 变量 | 含义 |
|------|------|
| `PAYPAL_PROXY_URL` / `PAYPAL_PROXY_POOL` | 默认代理（Web 填写优先） |
| `PAYPAL_ROXY_API_KEY` / HOST / PORT | Roxy Local API |
| `SMSBOWER_API_KEY` | 自动接码（可选） |
| `PAYPAL_FINGERPRINT_SOURCE` 等 | 细粒度运行时覆盖 |

**优先级**：Web/CLI 字段 > 环境变量 > `config.py`

## 4. 启动 Web

```powershell
.\start.bat
# 或
.\.venv\Scripts\python.exe web.py --host 127.0.0.1 --port 8080
```

打开：http://127.0.0.1:8080

### Web 默认（当前）

- 指纹 / DataDome / MTR = **本地 Headless**
- 业务：**实跑 A 层**（无 Merchant B/C 开关）
- 国家：可搜索中文下拉
- 代理：填写 +「测试代理」；任务头显示解析后的 proxy_label

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
.\.venv\Scripts\python.exe main.py --country NL --ba-token BA-xxx --phone +316... --proxy-url "socks5h://user:pass@host:port"
```

## 6. 代理详解

见 [PROXY.md](./PROXY.md)。

## 7. Roxy（可选）

1. 本机启动 RoxyBrowser Local API
2. Web Roxy 面板填 API Key，或设环境变量
3. 指纹/DataDome/MTR 选 roxy 或 auto
4. 创建窗口可绑定应用层代理；未填则显示「本机网络」

## 8. 测试

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest tests -q
```

## 9. 故障速查

| 现象 | 处理 |
|------|------|
| `WebJob() takes no arguments` | 确认 `WebJob` 带 `@dataclass` |
| `playwright is not installed` | 见上文 Headless 安装 |
| SOCKS5 认证与 Chromium | 见 PROXY.md 本地 HTTP 桥 |
| `forbidden ip not supported` | 白名单或开 TUN / 系统代理路径 |
| `curl 97` | 多为上游 HTTP 403，见 PROXY.md |
| `AWAITING_OTP` 发码失败 | 换号；代理通仍可能风控拒发 |

协议链路见 `PROTOCOL_CHAIN.md`、`README.md`。