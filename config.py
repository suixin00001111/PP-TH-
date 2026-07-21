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

# 代理请用 Web 填写或环境变量，勿提交真实账号
PROXY_ENABLED = False
USE_SYSTEM_PROXY = False
PROXY_POOL: list[str] = []

# ===== Browser + protocol runtime =====
RUNTIME_MODE = "protocol"

FINGERPRINT_SOURCE = "auto"
DATADOME_MODE = "auto"
DATADOME_ROXY_WAIT_SECONDS = 12.0
MTR_RUNTIME_MODE = "auto"
MTR_ROXY_WAIT_SECONDS = 20.0
MTR_CHANNEL = "iwc-mxo"
MTR_API_KEY = ""
RISK_SIGNALS_MODE = "auto"
RISK_ROXY_WAIT_SECONDS = 18.0

BROWSER_PROFILE = {
    "country": "TH",
    "language": "th-TH",
    "locale": "th_TH",
    "timezone": "Asia/Bangkok",
    "timezone_offset_minutes": -420,
    "timezone_offset_ms": -420 * 60 * 1000,
    "dst": False,
    "chrome_major": 150,
    "chrome_full_version": "150.0.0.0",
    "platform": "Linux x86_64",
    "sec_ch_platform": '"Linux"',
    "sec_ch_platform_version": '""',
    "sec_ch_arch": '"x86"',
    "device_memory": 8,
    "hardware_concurrency": 12,
    "device_pixel_ratio": 1,
    "connection_effective_type": "4g",
    "connection_rtt": "150",
    "connection_downlink": "10",
    "gpu_vendor": "Google Inc. (Google)",
    "gpu_renderer": "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)",
    "webgl_vendor": "WebKit",
    "webgl_renderer": "WebKit WebGL",
}

ROXY_API_HOST = "127.0.0.1"
ROXY_API_PORT = 50000
ROXY_API_KEY = ""
ROXY_HEADLESS = True
ROXY_WORKSPACE_ID = None
ROXY_PROJECT_ID = None

SMSBOWER_ENABLED = False
SMSBOWER_API_KEY = ""
SMSBOWER_SERVICE = "ts"
SMSBOWER_COUNTRY = "73"
SMSBOWER_WAIT_SECONDS = 30.0
SMSBOWER_POLL_INTERVAL_SECONDS = 2.0
