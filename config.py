USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)

SCREEN = {
    "colorDepth": 24,
    "pixelDepth": 24,
    "height": 1152,
    "width": 2048,
    "availHeight": 1152,
    "availWidth": 2048,
}

VIEWPORT = {"width": 1324, "height": 842}

TEALEAF_APP_KEY = "76938917d7504ff7a962174c021690bd"
HCAPTCHA_SITEKEY = "884d15d9-b649-4bbb-8d1c-2d6f0eed75eb"


# 代理配置（请勿把真实账号密码提交到 Git）
# 格式：host:port:username:password
# 推荐用环境变量注入：
#   PAYPAL_PROXY_ENABLED=1
#   PAYPAL_USE_SYSTEM_PROXY=0
#   PAYPAL_PROXY_POOL='host:port:username:password'
#   或 PAYPAL_PROXY_URL=http://user:pass@host:port
# USE_SYSTEM_PROXY=True 时会读取 Windows 系统代理（如 Clash 7897），
# 家宽直连请保持 False，并配置 PROXY_POOL / 环境变量。
PROXY_ENABLED = False
USE_SYSTEM_PROXY = False
PROXY_POOL: list[str] = [
    # 示例（请替换为你的家宽代理）：
    # "us.example-proxy.io:3010:username-region-TH:password",
]