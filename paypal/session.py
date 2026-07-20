import json
import os
from http.cookiejar import Cookie

import curl_cffi.requests as curl_requests
from loguru import logger
from typing import Any, Optional
from paypal.models import SessionState
from config import USER_AGENT


_LOCALE_BY_REGION = {"TH": "th-TH", "ID": "id-ID"}

# curl_cffi needs CA cert at an ASCII-only path on Windows
_CURL_CA_BUNDLE = os.environ.get("CURL_CA_BUNDLE", "")
if not _CURL_CA_BUNDLE:
    _cert_paths = [
        os.path.join(os.environ.get("TEMP", ""), "cacert.pem"),
        os.path.join(os.environ.get("TMP", ""), "cacert.pem"),
        "C:/Windows/Temp/cacert.pem",
    ]
    for p in _cert_paths:
        if os.path.isfile(p):
            _CURL_CA_BUNDLE = p
            break


def build_common_headers(country: str = "TH", locale: str = "") -> dict:
    country = (country or "TH").upper()
    language = locale or _LOCALE_BY_REGION.get(country, "en-US")
    return {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": f"{language},{language.split('-')[0]};q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Connection": "keep-alive",
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "sec-ch-ua-platform-version": '"6.1.0"',
        "sec-ch-ua-arch": '"x86"',
        "sec-ch-ua-bitness": '"64"',
        "sec-ch-ua-model": '""',
        "sec-ch-ua-wow64": "?0",
        "sec-ch-ua-form-factors": '"Desktop"',
        "sec-ch-ua-full-version-list": '"Not.A/Brand";v="99.0.0.0", "Chromium";v="150.0.6099.71", "Google Chrome";v="150.0.6099.71"',
        "sec-ch-device-memory": "32",
        "sec-gpc": "1",
    }


def _mask_middle(value: str, left: int = 6, right: int = 4) -> str:
    if len(value) <= left + right:
        return "<redacted>"
    return f"{value[:left]}...{value[-right:]}"


def _mask_email(value: str) -> str:
    if "@" not in value:
        return "<redacted>"
    local, domain = value.split("@", 1)
    if len(local) <= 2:
        return f"{local[:1]}***@{domain}"
    return f"{local[:2]}***{local[-1:]}@{domain}"


def _mask_digits(value: str, keep: int = 4) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) <= keep:
        return "<redacted>"
    return f"{'*' * (len(digits) - keep)}{digits[-keep:]}"


def sanitize_for_log(value: Any, key: str = "") -> Any:
    """Remove secrets and high-risk PII before writing diagnostics."""
    if isinstance(value, dict):
        return {k: sanitize_for_log(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_for_log(item, key) for item in value]
    if not isinstance(value, str):
        return value

    lowered_key = key.lower()
    compact_key = lowered_key.replace("_", "").replace("-", "")

    if compact_key in {"password", "securitycode", "cvv", "pin"}:
        return "<redacted>"
    if "authorization" in compact_key or "cookie" in compact_key or compact_key in {"cookies", "sessioncookies"}:
        return "<redacted>"
    if "accesstoken" in compact_key or "euat" in compact_key:
        return "<redacted>"
    if compact_key in {"token", "batoken", "ectoken", "billingagreementid"}:
        return _mask_middle(value)
    if compact_key in {"cardnumber", "encryptednumber"}:
        return _mask_digits(value)
    if compact_key in {"cpf", "identitydocument", "document", "value"}:
        return "<redacted>"
    if compact_key == "email":
        return _mask_email(value)
    if compact_key in {"phonenumber", "phone", "number"} and sum(ch.isdigit() for ch in value) >= 8:
        return _mask_digits(value)

    return value


def _paypal_debug_id(headers) -> str:
    for name in ("paypal-debug-id", "Paypal-Debug-Id", "PayPal-Debug-Id"):
        value = headers.get(name)
        if value:
            return value
    return ""


class PayPalSession:
    """Manages HTTP session with cookie persistence and logging.
    
    Uses curl_cffi with Chrome 131 impersonation for TLS fingerprint matching,
    which is critical for passing PayPal's DataDome bot detection.
    """

    def __init__(
        self,
        state: SessionState,
        proxy_url: str | None = None,
        proxy_label: str = "",
        country: str | None = None,
        locale: str | None = None,
    ):
        self.state = state
        self.country = (country or state.region or "TH").upper()
        self.locale = locale or _LOCALE_BY_REGION.get(self.country, "en-US")
        self.locale_tag = self.locale.replace("-", "_")
        self.proxy_url = proxy_url
        self.proxy_label = proxy_label or ("代理已开启" if proxy_url else "代理关闭")
        
        session_kwargs = {
            "impersonate": "chrome131",
            "timeout": 30,
            "allow_redirects": False,
            "headers": build_common_headers(self.country, self.locale),
        }
        if _CURL_CA_BUNDLE:
            session_kwargs["verify"] = _CURL_CA_BUNDLE
        
        self.client = curl_requests.Session(**session_kwargs)
        
        if proxy_url:
            self.client.proxies = {"http": proxy_url, "https": proxy_url}
        
        logger.info("HTTP outbound proxy: {}", self.proxy_label)

    def close(self):
        self.client.close()

    def _sync_state_cookies(self):
        """Pull important cookies into SessionState after each request."""
        cookie_dict = {}
        # curl_cffi cookies are iterable as (name, value) pairs or Cookie objects
        try:
            for cookie in self.client.cookies:
                if isinstance(cookie, str):
                    continue
                if hasattr(cookie, "name") and hasattr(cookie, "value"):
                    cookie_dict[cookie.name] = cookie.value
                elif len(cookie) == 2:
                    cookie_dict[cookie[0]] = cookie[1]
        except Exception:
            pass
        self.state.update_from_cookies(cookie_dict)

    def get(self, url: str, **kwargs):
        logger.debug(f"GET {url}")
        resp = self.client.get(url, **kwargs)
        self._sync_state_cookies()
        logger.debug(f"  -> {resp.status_code} ({len(resp.content)} bytes)")
        return resp

    def post(self, url: str, **kwargs):
        logger.debug(f"POST {url}")
        resp = self.client.post(url, **kwargs)
        self._sync_state_cookies()
        logger.debug(f"  -> {resp.status_code} ({len(resp.content)} bytes)")
        return resp

    def graphql(self, operation_name: str, query: str, variables: dict,
                extra_headers: Optional[dict] = None,
                extra_body: Optional[dict] = None,
                batched: bool = False,
                endpoint: Optional[str] = None) -> dict:
        """Send a GraphQL request to PayPal's graphql endpoint."""
        url = endpoint or "https://www.paypal.com/graphql"
        if operation_name and endpoint is None:
            url = f"{url}?{operation_name}"

        context_token = str(
            variables.get("token")
            or variables.get("billingAgreementId")
            or self.state.ec_token
            or self.state.ba_token
        )
        referer = (
            self.state.signup_url
            if self.state.ec_token
            else f"https://www.paypal.com/pay?token={self.state.ba_token}&ul=1"
        )
        app_name = "checkoutuinodeweb" if operation_name == "authorize" else "checkoutuinodeweb_weasley"
        headers = {
            "Content-Type": "application/json",
            "X-App-Name": app_name,
            "X-Requested-With": "fetch",
            "PayPal-Client-Context": context_token,
            "PayPal-Client-Metadata-Id": context_token,
            "X-Country": self.country,
            "X-Locale": self.locale_tag,
            "Origin": "https://www.paypal.com",
            "Referer": referer,
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }
        if self.state.euat_token:
            headers["X-PayPal-Internal-EUAT"] = self.state.euat_token
        if extra_headers:
            for key, value in extra_headers.items():
                if value is None:
                    headers.pop(key, None)
                else:
                    headers[key] = value

        payload_item = {
            "operationName": operation_name,
            "variables": variables,
            "query": query,
        }
        if extra_body:
            payload_item.update(extra_body)

        payload = [payload_item] if batched else payload_item

        resp = self.post(url, json=payload, headers=headers)
        debug_id = _paypal_debug_id(resp.headers)
        logger.info(
            "GraphQL {} HTTP {} bytes={} paypal_debug_id={}",
            operation_name,
            resp.status_code,
            len(resp.content),
            debug_id or "<missing>",
        )

        try:
            result = resp.json()
        except ValueError:
            logger.error(
                "GraphQL {} returned non-JSON response: status={} paypal_debug_id={} body={}",
                operation_name,
                resp.status_code,
                debug_id or "<missing>",
                resp.text[:2000],
            )
            raise

        result_items = result if isinstance(result, list) else [result]
        for item in result_items:
            if not isinstance(item, dict) or not item.get("errors"):
                continue

            logger.error(
                "GraphQL {} returned errors: status={} paypal_debug_id={} errors={}",
                operation_name,
                resp.status_code,
                debug_id or "<missing>",
                json.dumps(
                    sanitize_for_log(item.get("errors")),
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            logger.debug(
                "GraphQL {} sanitized variables: {}",
                operation_name,
                json.dumps(
                    sanitize_for_log(variables),
                    ensure_ascii=False,
                    indent=2,
                ),
            )

        return result
