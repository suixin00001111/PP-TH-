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


# 代理请用 Web 页面填写或环境变量注入，勿提交真实账号
PROXY_ENABLED = False
USE_SYSTEM_PROXY = False
PROXY_POOL: list[str] = []