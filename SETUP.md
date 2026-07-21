# 环境安装速查

## 1. 基础

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 2. Headless（Playwright + Chromium）

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-headless.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

验证：

```powershell
.\.venv\Scripts\python.exe -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); print('OK', b.version); b.close(); p.stop()"
```

## 3. RoxyBrowser（可选）

1. 安装并启动 RoxyBrowser 客户端  
2. 开启 Local API  
3. 设置环境变量 `PAYPAL_ROXY_API_KEY` / `HOST` / `PORT`  
4. 运行时选 `auto` 或 `roxy`

## 4. 启动

```powershell
.\start.bat
# http://127.0.0.1:8080
```

Web 选择：协议国家、运行时（protocol/headless/auto）、代理、可选 SMSBower。

## 5. CLI 示例

```powershell
# 纯协议
.\.venv\Scripts\python.exe main.py --country TH --ba-token BA-xxx --phone +6681... --runtime protocol

# Headless 风控
.\.venv\Scripts\python.exe main.py --country JP --ba-token BA-xxx --phone +8190... --runtime headless --proxy

# 自动接码（巴西示例）
.\.venv\Scripts\python.exe main.py --country BR --ba-token BA-xxx --smsbower --smsbower-api-key KEY --runtime auto
```
