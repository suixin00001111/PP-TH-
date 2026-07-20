"""Main PayPal Billing Agreement approval flow orchestrator.

Implements the complete protocol:
  Phase 0: DataDome verification + initial page load
  Phase 1: Device fingerprint + Tealeaf + analytics beacons
  Phase 2: Create account (email submission → signup page)
  Phase 3: Fill signup form + submit (triggers 2FA SMS)
  Phase 4: OTP verification + final authorize mutation
"""
import re
import time
import json
import urllib.parse
from loguru import logger

import curl_cffi

from paypal.models import (
    SessionState,
    UserInfo,
    CardInfo,
    BillingAddress,
)
from paypal.oaipy_data import (
    generate_card,
    generate_random_email,
)
from paypal.session import PayPalSession, sanitize_for_log
from paypal.proxy import build_proxy_config, ProxyConfig
from paypal.regions import get_region, normalize_phone
from paypal.protocol import build_protocol, format_billing_line1, format_billing_line2
from paypal.fingerprint import (
    build_fn_sync_data,
    build_signup_fn_sync_data,
    send_device_fingerprint,
    send_signup_field_events,
)
from paypal.tealeaf import send_tealeaf_data
from paypal.analytics import (
    send_xo_logger,
    send_analytics_ts,
    send_observability_emit,
    send_weasley_log,
)
from paypal.b_layer_handoff import build_b_layer_evidence
from paypal.graphql import (
    CHECKOUT_SESSION_DATA_QUERY,
    GRIFFIN_METADATA_QUERY,
    SUPPORTED_FUNDING_SOURCES_QUERY,
    DEFERRED_FEATURE_QUERY,
    INSTALLMENT_OPTIONS_QUERY,
    ADDRESS_AUTOCOMPLETE_FROM_POSTAL_CODE_QUERY,
    INITIATE_2FA_PHONE_MUTATION,
    CONFIRM_2FA_PHONE_MUTATION,
    SIGNUP_NEW_MEMBER_MUTATION,
    AUTHORIZE_BILLING_MUTATION,
)


REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
BA_TOKEN_RE = re.compile(r"^BA-[A-Za-z0-9]{8,80}$")
EC_TOKEN_RE = re.compile(r"^EC-[A-Za-z0-9]{8,80}$")


class PayPalFlow:
    def __init__(
        self,
        ba_token: str,
        user: UserInfo,
        card: CardInfo,
        address: BillingAddress,
        max_card_attempts: int = 5,
        proxy_enabled: bool | None = None,
        proxy_index: int | None = None,
        proxy_config: ProxyConfig | None = None,
    ):
        ba_token = (ba_token or "").strip()
        if not BA_TOKEN_RE.fullmatch(ba_token):
            raise ValueError("invalid PayPal BA token format")
        self.ba_token = ba_token
        self.user = user
        if not self.user.email:
            self.user.email = generate_random_email()
        self.card = card
        self.address = address
        self.max_card_attempts = max(1, max_card_attempts)
        self.proxy_config: ProxyConfig = proxy_config or build_proxy_config(
            enabled=proxy_enabled,
            index=proxy_index,
        )
        # Bind country protocol context (TH is reference machine; not TH constants).
        self.protocol = build_protocol(self.address.country)
        self.address.country = self.protocol.code
        self.state = SessionState(ba_token=ba_token, region=self.protocol.code)
        self._update_user_phone(self.user.phone)
        self.session = PayPalSession(
            self.state,
            proxy_url=self.proxy_config.url,
            proxy_label=self.proxy_config.label,
            country=self.protocol.code,
            locale=self.protocol.locale_bcp47,
        )
        logger.info(
            "Protocol context: {} ({}) lang={} locale={} phone_cc={}",
            self.protocol.code,
            self.protocol.name_zh,
            self.protocol.lang,
            self.protocol.locale_tag,
            self.protocol.phone_cc,
        )

    def close(self):
        self.session.close()

    @property
    def region_profile(self):
        return get_region(self.address.country)

    @property
    def lang(self) -> str:
        return getattr(self, "protocol", None).lang if getattr(self, "protocol", None) else self.region_profile.lang

    def _ensure_protocol(self):
        if not getattr(self, "protocol", None):
            self.protocol = build_protocol(self.address.country)
        return self.protocol

    @staticmethod
    def _is_generic_error_response(resp) -> bool:
        url = str(getattr(resp, "url", "") or "").lower()
        return "/generic-error" in urllib.parse.urlparse(url).path

    @staticmethod
    def _is_datadome_challenge_response(resp) -> bool:
        if getattr(resp, "status_code", 0) == 403:
            return True
        text = (getattr(resp, "text", "") or "")[:50000].lower()
        markers = (
            "captcha-delivery.com",
            "datadome.co/captcha",
            "ct.ddc.paypal.com/c.js",
            "ywrzzgrjyxb0y2hh",
        )
        return any(marker in text for marker in markers)

    def _validate_paypal_response(self, resp, stage: str) -> None:
        if self._is_datadome_challenge_response(resp):
            raise RuntimeError(
                f"{stage}: DataDome challenge detected; a solved browser session is required"
            )
        if self._is_generic_error_response(resp):
            raise RuntimeError(f"{stage}: PayPal redirected to generic-error")
        status_code = int(getattr(resp, "status_code", 0) or 0)
        if status_code >= 400 or status_code == 0:
            raise RuntimeError(f"{stage}: unexpected HTTP status {status_code}")

    def _follow_paypal_redirects(self, resp, *, stage: str, referer: str = "", max_hops: int = 8):
        """Follow a bounded PayPal redirect chain and reject known error destinations."""
        current_referer = referer
        for _ in range(max_hops):
            if getattr(resp, "status_code", 0) not in REDIRECT_STATUS_CODES:
                self._validate_paypal_response(resp, stage)
                return resp
            location = (getattr(resp, "headers", {}) or {}).get("Location", "")
            if not location:
                raise RuntimeError(f"{stage}: redirect response did not include Location")
            redirect_url = urllib.parse.urljoin(str(getattr(resp, "url", "")), location)
            if "/generic-error" in urllib.parse.urlparse(redirect_url.lower()).path:
                raise RuntimeError(f"{stage}: PayPal redirected to generic-error")
            logger.info(f"Following redirect: {redirect_url[:140]}...")
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Priority": "u=0, i",
            }
            if current_referer:
                headers["Referer"] = current_referer
            resp = self.session.get(redirect_url, headers=headers)
            current_referer = str(getattr(resp, "url", ""))
        raise RuntimeError(f"{stage}: redirect limit exceeded")

    @staticmethod
    def _extract_ec_token(resp) -> str:
        parsed = urllib.parse.urlparse(str(getattr(resp, "url", "") or ""))
        query = urllib.parse.parse_qs(parsed.query)
        for key in ("token", "ec_token"):
            for value in query.get(key, []):
                if EC_TOKEN_RE.fullmatch(value):
                    return value
        match = re.search(r"\bEC-[A-Za-z0-9]{8,80}\b", getattr(resp, "text", "") or "")
        return match.group(0) if match else ""

    def _require_ec_token(self, stage: str) -> str:
        token = (self.state.ec_token or "").strip()
        if not EC_TOKEN_RE.fullmatch(token):
            raise RuntimeError(
                f"{stage}: no valid EC token; refusing to substitute the BA token"
            )
        return token

    def _validate_signup_response(self, resp) -> None:
        self._validate_paypal_response(resp, "Phase 2 checkout signup")
        path = urllib.parse.urlparse(str(getattr(resp, "url", "") or "")).path.lower()
        if "/checkoutweb/signup" not in path:
            raise RuntimeError(
                f"Phase 2 checkout signup: unexpected destination {path or '<empty>'}"
            )
        html = getattr(resp, "text", "") or ""
        markers = (
            "window.__INITIAL_DATA__",
            "checkoutweb",
            "weasley",
            "SignUpNewMemberMutation",
            "compliance.signupTerms",
        )
        if len(html) < 100 or not any(marker.lower() in html.lower() for marker in markers):
            raise RuntimeError("Phase 2 checkout signup: signup application context is missing")

    @staticmethod
    def _require_checkout_session(result) -> None:
        item = result[0] if isinstance(result, list) and result else result
        if not isinstance(item, dict):
            raise RuntimeError("CheckoutSessionDataQuery returned an invalid response")
        if item.get("errors"):
            messages = [
                str(error.get("message") or error.get("name") or "unknown error")
                for error in item.get("errors", [])
                if isinstance(error, dict)
            ]
            detail = ", ".join(messages[:3]) or "GraphQL error"
            raise RuntimeError(f"CheckoutSessionDataQuery rejected the EC context: {detail}")
        checkout_session = (item.get("data") or {}).get("checkoutSession")
        if not isinstance(checkout_session, dict):
            raise RuntimeError("CheckoutSessionDataQuery returned no checkoutSession")
        if checkout_session.get("checkoutSessionType") != "BILLING_WITHOUT_PURCHASE":
            raise RuntimeError(
                "CheckoutSessionDataQuery returned an unexpected checkout session type"
            )

    def _require_signup_context(self, stage: str) -> str:
        token = self._require_ec_token(stage)
        if (
            not self.state.signup_context_ready
            or not self.state.signup_url
            or not self.state.content_identifier
        ):
            raise RuntimeError(f"{stage}: checkout signup context was not validated")
        return token

    def run(self) -> dict:
        """Execute the complete flow. Returns result dict with status and return_url."""
        try:
            logger.info(f"=== PayPal Billing Agreement Flow ===")
            logger.info("BA Token: {}", sanitize_for_log({"ba_token": self.ba_token})["ba_token"])
            logger.info("Email: {}", sanitize_for_log({"email": self.user.email})["email"])
            logger.info("Phone: {}", sanitize_for_log({"phone": self.user.phone})["phone"])
            logger.info(f"Proxy: {self.proxy_config.label}")

            self._phase0_initial_load()
            self._phase1_risk_controls()
            self._phase2_create_account()
            self._phase3_signup_and_2fa()
            result = self._phase4_authorize()

            if result.get("status") == "success":
                logger.success(f"=== Flow completed successfully ===")
            else:
                logger.error(f"=== Flow completed with error status ===")
            return result
        except Exception as e:
            logger.error(f"Flow failed: {e}")
            raise
        finally:
            self.close()

    def _phase0_initial_load(self):
        """Load the agreement approval page, handle DataDome if needed."""
        logger.info("--- Phase 0: Initial page load ---")

        url = f"https://www.paypal.com/agreements/approve?ba_token={self.ba_token}"

        max_retries = 4
        for attempt in range(max_retries):
            if attempt > 0:
                delay = 2 + attempt * 2
                logger.info(f"Phase 0 retry {attempt}/{max_retries - 1} after {delay}s delay...")
                time.sleep(delay)
                # Recreate session with fresh proxy connection (may get different exit IP)
                self.session.close()
                proto = self._ensure_protocol()
                self.session = PayPalSession(
                    self.state,
                    proxy_url=self.proxy_config.url,
                    proxy_label=self.proxy_config.label,
                    country=proto.code,
                    locale=proto.locale_bcp47,
                )

            # First GET - may return 403 with DataDome challenge or 302 redirect
            resp = self.session.get(url, headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Priority": "u=0, i",
            })

            if resp.status_code == 403:
                if attempt < max_retries - 1:
                    logger.warning("Phase 0: DataDome 403, will retry...")
                    continue
                raise RuntimeError(
                    "Phase 0: DataDome challenge detected after all retries; an empty adsddtoken is not a valid solution"
                )

            break  # success

        if resp.status_code in REDIRECT_STATUS_CODES:
            redirect_url = urllib.parse.urljoin(str(resp.url), resp.headers.get("Location", ""))
            ssrt_match = re.search(r"ssrt=(\d+)", redirect_url)
            if ssrt_match:
                self.state.ssrt = ssrt_match.group(1)
        resp = self._follow_paypal_redirects(resp, stage="Phase 0 initial load", referer=url)

        # Parse the login/signup page
        html = resp.text
        logger.info(f"Page loaded: {resp.status_code}, {len(html)} bytes")
        self._extract_modxo_action_ids(html, str(resp.url))

        # Extract ctxId
        ctx_match = re.search(r'"ctxId"[^"]*"([^"]+)"', html)
        if ctx_match:
            self.state.ctx_id = ctx_match.group(1)
            logger.info(f"Context ID: {self.state.ctx_id}")

        # Extract ssrt if not yet found
        if not self.state.ssrt:
            ssrt_match = re.search(r"ssrt=(\d+)", str(resp.url))
            if not ssrt_match:
                ssrt_match = re.search(r"ssrt=(\d+)", html)
            if ssrt_match:
                self.state.ssrt = ssrt_match.group(1)
                logger.info(f"SSRT: {self.state.ssrt}")

    @staticmethod
    def _extract_window_initial_data(html: str) -> dict:
        """Extract checkoutweb/weasley window.__INITIAL_DATA__ JSON."""
        # The page contains many reads of window.__INITIAL_DATA__ before the
        # actual server-side assignment.  Anchor on `= {` so we do not parse a
        # JavaScript function body from an earlier reference.
        marker = re.search(r"window\.__INITIAL_DATA__\s*=", html or "")
        if not marker:
            return {}

        start = html.find("{", marker.end())
        if start < 0:
            return {}

        depth = 0
        in_str = False
        escape = False
        for idx in range(start, len(html)):
            ch = html[idx]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue

            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[start:idx + 1])
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse __INITIAL_DATA__: {e}")
                        return {}

        return {}

    @staticmethod
    def _extract_content_identifier(html: str, country: str = "TH", lang: str = "") -> str:
        """Extract or build the dynamic signup terms contentIdentifier."""
        if not lang:
            from paypal.regions import get_region
            lang = get_region(country).lang
        for pattern in (
            r'"contentIdentifier"\s*:\s*"([^"]*signupTerms[^"]*)"',
            r'\\"contentIdentifier\\"\s*:\s*\\"([^"\\]*signupTerms[^"\\]*)\\"',
            r'([A-Z]{2}:[a-z]{2}:[0-9a-f]{16,64}:compliance\.signupTerms)',
        ):
            match = re.search(pattern, html or "", re.I)
            if match:
                return match.group(1).replace("\\/", "/")
        return f"{country}:{lang}:compliance.signupTerms"

    def _build_signup_url(self) -> str:
        """Build the canonical checkoutweb/signup URL used as GraphQL Referer."""
        params: list[tuple[str, str]] = []
        if self.state.ssrt:
            params.append(("ssrt", self.state.ssrt))
        params.extend([
            ("ul", "1"),
            ("modxo_redirect_reason", "guest_user"),
            ("locale.x", self._ensure_protocol().locale_x),
            ("country.x", self._ensure_protocol().country_x),
            ("ba_token", self.ba_token),
            ("token", self.state.ec_token),
            ("rcache", "1"),
            ("cookieBannerVariant", "hidden"),
        ])
        return "https://www.paypal.com/checkoutweb/signup?" + urllib.parse.urlencode(params)

    @staticmethod
    def _extract_onboarding_redirect(rsc_text: str) -> str:
        """Extract onboardingRedirectUrl from Next/RSC server-action response."""
        match = re.search(r'"onboardingRedirectUrl"\s*:\s*"([^"]+)"', rsc_text or "")
        if not match:
            return ""
        return match.group(1).replace("\\/", "/")

    @staticmethod
    def _find_access_token(value) -> str:
        """Find an accessToken recursively in GraphQL data/errorData."""
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "accessToken" and isinstance(item, str) and item:
                    return item
                found = PayPalFlow._find_access_token(item)
                if found:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = PayPalFlow._find_access_token(item)
                if found:
                    return found
        return ""

    @staticmethod
    def _has_buyer_not_set(result) -> bool:
        items = result if isinstance(result, list) else [result]
        for item in items:
            if not isinstance(item, dict):
                continue
            for err in item.get("errors") or []:
                data = err.get("data") or {}
                if data.get("contingency") == "BUYER_NOT_SET":
                    return True
                if err.get("message") == "BUYER_NOT_SET":
                    return True
        return False

    def _extract_modxo_action_ids(self, html: str, base_url: str):
        """Extract Next server-action IDs from ModXO JS chunks.

        The browser sends these values in the Next-Action header. They are
        deployment-specific, so hard-coding the values from one capture breaks
        after PayPal ships a new bundle.
        """
        action_names = {
            "show_create_account_action_id": "showCreateAccountAction",
            "create_user_action_id": "createUserAction",
        }

        def scan(text: str) -> bool:
            changed = False
            for attr, action_name in action_names.items():
                if getattr(self.state, attr):
                    continue
                name_idx = text.find(f'"{action_name}"')
                if name_idx < 0:
                    continue
                window = text[max(0, name_idx - 500):name_idx]
                ids = re.findall(r'"([0-9a-f]{32,64})"', window)
                if ids:
                    action_id = ids[-1]
                    setattr(self.state, attr, action_id)
                    logger.info(f"ModXO action {attr}: {action_id}")
                    changed = True
            return changed

        scan(html or "")
        if self.state.show_create_account_action_id and self.state.create_user_action_id:
            return

        script_urls = []
        for src in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html or "", re.I):
            if "/pay/_next/static/chunks/" not in src:
                continue
            url = urllib.parse.urljoin(base_url, src)
            if url not in script_urls:
                script_urls.append(url)

        for script_url in script_urls[:80]:
            try:
                js_resp = self.session.get(
                    script_url,
                    headers={
                        "Accept": "*/*",
                        "Referer": base_url,
                        "Sec-Fetch-Dest": "script",
                        "Sec-Fetch-Mode": "no-cors",
                        "Sec-Fetch-Site": "same-origin",
                    },
                )
                if js_resp.status_code == 200:
                    scan(js_resp.text)
                if self.state.show_create_account_action_id and self.state.create_user_action_id:
                    return
            except Exception as e:
                logger.debug(f"Failed to inspect ModXO chunk {script_url}: {e}")

    def _card_issuer_type(self) -> str:
        """PayPal GraphQL CardIssuerType enum."""
        prefix2 = int(self.card.number[:2]) if self.card.number[:2].isdigit() else 0
        prefix4 = int(self.card.number[:4]) if self.card.number[:4].isdigit() else 0
        if 51 <= prefix2 <= 55 or 2221 <= prefix4 <= 2720:
            return "MASTER_CARD"
        if self.card.number.startswith("4"):
            return "VISA"
        if self.card.number.startswith("3"):
            return "AMEX"
        if self.card.number.startswith("6"):
            return "DISCOVER"
        return "VISA"

    def _masked_card_number(self) -> str:
        return sanitize_for_log({"cardNumber": self.card.number})["cardNumber"]

    def _masked_phone(self) -> str:
        return sanitize_for_log({"phone": self.user.phone})["phone"]

    def _update_user_phone(self, phone: str):
        """Update phone fields used by signup/2FA GraphQL calls (region-aware)."""
        raw = (phone or "").strip()
        if raw.lower().startswith("phone:"):
            raw = raw.split(":", 1)[1].strip()
        e164, local, country_code = normalize_phone(self.address.country, raw)
        self.user.phone = e164
        self.user.phone_country_code = country_code
        self.user.phone_local = local
        logger.info("Phone updated for OTP retry: {}", self._masked_phone())

    def _initiate_2fa_phone_confirmation(self, token: str, signup_url: str) -> tuple[str, str]:
        """Send a new 2FA SMS and return authId/challengeId."""
        logger.info("Step 1: Initiating 2FA phone confirmation for {}...", self._masked_phone())
        send_weasley_log(
            self.session,
            self.state.ec_token,
            signup_url,
            [
                "weasley_risk_based_phone_confirmation_modal_component_mounted",
                "weasley_initiate_phone_confirmation_start",
                "weasley_api_request_initiate_risk_based_two_factor_phone_confirmation_mutation",
            ],
            country=self.address.country,
            lang=self.lang,
        )
        initiate_result = self.session.graphql(
            "InitiateRiskBasedTwoFactorPhoneConfirmationMutation",
            INITIATE_2FA_PHONE_MUTATION,
            {
                "phoneNumber": self.user.phone_local,
                "locale": {
                    "country": self.address.country.upper(),
                    "lang": self.address.country.lower(),
                },
                "phoneCountry": self.address.country.upper(),
                "token": token,
            },
        )
        logger.info(
            "2FA initiation result (sanitized): {}",
            json.dumps(sanitize_for_log(initiate_result), ensure_ascii=False, indent=2)[:500],
        )

        result_obj = initiate_result[0] if isinstance(initiate_result, list) else initiate_result
        tfa_data = result_obj.get("data", {}).get(
            "initiateRiskBasedTwoFactorPhoneConfirmation", {}
        )
        auth_id = tfa_data.get("authId", "")
        challenge_id = tfa_data.get("challengeId", "")
        state = tfa_data.get("state", "")
        logger.info("2FA state: {}, authId=<redacted>, challengeId=<redacted>", state)

        if not auth_id or not challenge_id:
            raise RuntimeError("Failed to get authId/challengeId from 2FA initiation")
        return auth_id, challenge_id

    def _confirm_2fa_phone_confirmation(
        self,
        token: str,
        signup_url: str,
        auth_id: str,
        challenge_id: str,
        otp: str,
    ) -> bool:
        """Confirm one OTP attempt. Return True only on CONFIRMED."""
        logger.info("Step 2: Confirming OTP: <redacted>")
        send_weasley_log(
            self.session,
            self.state.ec_token,
            signup_url,
            [
                "weasley_confirm_phone_confirmation_start",
                "weasley_api_request_confirm_risk_based_two_factor_phone_confirmation_mutation",
            ],
            country=self.address.country,
            lang=self.lang,
        )
        confirm_result = self.session.graphql(
            "ConfirmRiskBasedTwoFactorPhoneConfirmationMutation",
            CONFIRM_2FA_PHONE_MUTATION,
            {
                "pin": otp,
                "authId": auth_id,
                "challengeId": challenge_id,
                "token": token,
            },
        )
        logger.info(
            "OTP confirmation result (sanitized): {}",
            json.dumps(sanitize_for_log(confirm_result), ensure_ascii=False, indent=2)[:500],
        )

        result_obj = confirm_result[0] if isinstance(confirm_result, list) else confirm_result
        confirm_data = result_obj.get("data", {}).get(
            "confirmRiskBasedTwoFactorPhoneConfirmation", {}
        ) or {}
        confirm_state = confirm_data.get("state", "")
        if confirm_state == "CONFIRMED":
            logger.success("OTP confirmed successfully!")
            return True

        errors = result_obj.get("errors") or []
        if errors:
            logger.warning(
                "OTP confirmation failed with errors: {}",
                json.dumps(sanitize_for_log(errors), ensure_ascii=False, indent=2),
            )
        else:
            logger.warning("OTP confirmation failed, state: {}", confirm_state or "<missing>")
        return False

    def _confirm_phone_with_retry(self, token: str, signup_url: str):
        """Loop until OTP is confirmed; user can enter a new phone to resend."""
        while True:
            try:
                auth_id, challenge_id = self._initiate_2fa_phone_confirmation(token, signup_url)
            except Exception as e:
                logger.error("Failed to initiate OTP for {}: {}", self._masked_phone(), e)
                while True:
                    value = input(
                        "\n>>> 发送验证码失败。请输入新的手机号重新发送"
                        f"（如 {self._ensure_protocol().phone_placeholder}）；输入 q 退出: "
                    ).strip()
                    if value.lower() in {"q", "quit", "exit"}:
                        raise RuntimeError("OTP confirmation cancelled by user") from e
                    try:
                        self._update_user_phone(value)
                        break
                    except ValueError as phone_error:
                        logger.warning("手机号无效：{}。请重新输入。", phone_error)
                continue
            logger.info("SMS verification code sent to phone: {}", self._masked_phone())

            while True:
                value = input(
                    "\n>>> 输入6位短信验证码；如需换号，直接输入新手机号"
                    f"（如 {self._ensure_protocol().phone_placeholder} 或 phone:{self._ensure_protocol().phone_placeholder}）；输入 q 退出: "
                ).strip()

                if value.lower() in {"q", "quit", "exit"}:
                    raise RuntimeError("OTP confirmation cancelled by user")

                if len(value) == 6 and value.isdigit():
                    if self._confirm_2fa_phone_confirmation(
                        token,
                        signup_url,
                        auth_id,
                        challenge_id,
                        value,
                    ):
                        return
                    logger.warning(
                        "验证码验证失败。可以继续输入新的6位验证码，或输入新手机号重新发送验证码。"
                    )
                    continue

                try:
                    self._update_user_phone(value)
                    logger.info("Re-sending OTP to the new phone...")
                    break
                except ValueError as e:
                    logger.warning(
                        "输入既不是6位验证码，也不是有效手机号：{}。请重新输入。",
                        e,
                    )

    def _card_expiration_date(self) -> str:
        exp_parts = self.card.expiry.split("/")
        return f"{exp_parts[0]}/{exp_parts[1]}" if len(exp_parts) == 2 else self.card.expiry

    def _dob_payload(self) -> dict:
        dob_parts = self.user.dob.split("/")
        return (
            {"day": dob_parts[0], "month": dob_parts[1], "year": dob_parts[2]}
            if len(dob_parts) == 3
            else {}
        )

    def _build_signup_variables(self, token: str) -> dict:
        card_type = self._card_issuer_type()
        return {
            "card": {
                "cardNumber": self.card.number,
                "expirationDate": self._card_expiration_date(),
                "securityCode": self.card.cvv,
                "type": card_type,
                "productClass": self.card.card_type,
            },
            "country": self._ensure_protocol().code,
            "email": self.user.email,
            "firstName": self.user.first_name,
            "lastName": self.user.last_name,
            "phone": {
                "countryCode": self.user.phone_country_code.lstrip("+"),
                "number": self.user.phone_local,
                "type": "MOBILE",
            },
            "supportedThreeDsExperiences": ["IFRAME"],
            "token": token,
            "billingAddress": {
                "postalCode": self.address.postal_code,
                "line1": format_billing_line1(
                    self._ensure_protocol().address_style,
                    self.address.street,
                    self.address.house_number,
                    self.address.district,
                ),
                "line2": format_billing_line2(
                    self._ensure_protocol().address_style,
                    self.address.district,
                ),
                "city": self.address.city,
                "state": self.address.state,
                "accountQuality": {
                    "autoCompleteType": "ANS",
                    "isUserModified": True,
                },
                "country": self._ensure_protocol().code,
                "familyName": self.user.last_name,
                "givenName": self.user.first_name,
            },
            "shippingAddress": {
                "postalCode": "",
                "line1": "",
                "city": "",
                "state": "",
                "accountQuality": {
                    "autoCompleteType": "MANUAL",
                    "isUserModified": False,
                },
                "country": self._ensure_protocol().code,
                "familyName": self.user.last_name,
                "givenName": self.user.first_name,
            },
            "contentIdentifier": self.state.content_identifier,
            "marketingOptOut": True,
            "password": self.user.password,
            "dateOfBirth": self._dob_payload(),
            # Regional identity: Thailand-base path uses null except BR CPF.
            "identityDocument": self._identity_document_payload(),
            "crsData": None,
            "legalAgreements": {},
        }


    def _identity_document_payload(self):
        """Build identityDocument for SignUpNewMember (country protocol)."""
        region = self._ensure_protocol()
        if not region.send_identity_document:
            return None
        if region.identity_type == "CPF":
            value = (self.user.cpf or self.user.national_id or "").replace(".", "").replace("-", "").strip()
            if not value:
                return None
            return {"type": "CPF", "value": value}
        return None

    def _send_signup_attempt(self, token: str, signup_url: str) -> dict:
        card_type = self._card_issuer_type()
        try:
            self.session.graphql(
                "InstallmentOptionsQuery",
                INSTALLMENT_OPTIONS_QUERY,
                {
                    "buyerCountry": self.address.country,
                    "cardNumber": self.card.number,
                    "cardType": card_type,
                    "token": token,
                },
            )
        except Exception as e:
            logger.warning(f"InstallmentOptionsQuery failed: {e}")

        send_signup_field_events(
            self.session,
            token,
            [
                "email",
                "phone",
                "cardNumber",
                "cardExpiry",
                "cardCvv",
                "password",
                "firstName",
                "lastName",
                "billingLine1",
                "billingCity",
                "billingPostalCode",
                "billingState",
                "dateOfBirth",
            ],
        )
        send_weasley_log(
            self.session,
            self.state.ec_token,
            signup_url,
            [
                "weasley_create_account_and_pay_submit",
                "weasley_api_request_sign_up_new_member_mutation",
            ],
            country=self.address.country,
            lang=self.lang,
        )
        signup_result = self.session.graphql(
            "SignUpNewMemberMutation",
            SIGNUP_NEW_MEMBER_MUTATION,
            self._build_signup_variables(token),
            extra_body={"fn_sync_data": build_signup_fn_sync_data(token)},
        )
        logger.info(
            "Signup result (sanitized): {}",
            json.dumps(
                sanitize_for_log(signup_result),
                ensure_ascii=False,
                indent=2,
            )[:4000],
        )
        return signup_result

    def _consume_signup_result(self, signup_result) -> tuple[bool, list[dict]]:
        """Apply successful signup data to state. Return (success, errors)."""
        result_obj = signup_result[0] if isinstance(signup_result, list) else signup_result
        onboard_data = result_obj.get("data", {}).get("onboardAccount", {})
        if onboard_data:
            buyer = onboard_data.get("buyer", {})
            self.state.user_id = buyer.get("userId", "")
            auth = buyer.get("auth", {})
            if auth:
                self.state.euat_token = auth.get("accessToken", "")
            logger.success(f"Account created! User ID: {self.state.user_id}")
            return True, []

        errors = result_obj.get("errors", []) or []
        if errors:
            for err in errors:
                logger.error(
                    "Signup error detail: {}",
                    json.dumps(
                        sanitize_for_log({
                            "message": err.get("message"),
                            "name": err.get("_name"),
                            "statusCode": err.get("statusCode"),
                            "checkpoints": err.get("checkpoints"),
                            "contingency": err.get("contingency"),
                            "path": err.get("path"),
                            "data": err.get("data"),
                            "errorData": err.get("errorData"),
                            "meta": err.get("meta"),
                            "extensions": err.get("extensions"),
                        }),
                        ensure_ascii=False,
                        indent=2,
                    ),
                )
        logger.error(
            "Signup failed because onboardAccount is empty. Sanitized response: {}",
            json.dumps(
                sanitize_for_log(result_obj),
                ensure_ascii=False,
                indent=2,
            )[:8000],
        )
        return False, errors

    @staticmethod
    def _dict_contains_card_field(value) -> bool:
        if isinstance(value, dict):
            for key, item in value.items():
                compact_key = str(key).lower().replace("_", "").replace("-", "")
                if compact_key in {"cardnumber", "card", "cardnumberfield"}:
                    return True
                if isinstance(item, str):
                    item_lower = item.lower()
                    if item_lower in {"cardnumber", "card_generic_error"}:
                        return True
                if PayPalFlow._dict_contains_card_field(item):
                    return True
        elif isinstance(value, list):
            return any(PayPalFlow._dict_contains_card_field(item) for item in value)
        return False

    @staticmethod
    def _is_card_related_signup_error(errors: list[dict]) -> bool:
        card_messages = {
            "CARD_GENERIC_ERROR",
            "INSTRUMENT_SHARING_LIMIT_EXCEEDED",
            "CC_LINKED_TO_FULL_ACCOUNT",
            "CREATE_CARD_ACCOUNT_CANDIDATE_VALIDATION_ERROR",
        }
        for err in errors or []:
            checkpoints = set(err.get("checkpoints") or [])
            if checkpoints.intersection({"addCard", "validate.fi", "card", "fi"}):
                return True
            message = str(err.get("message") or "")
            if message in card_messages:
                return True
            # PayPal backend sometimes returns destructuring errors during
            # card BIN validation; treat these as card-related so retries
            # generate fresh card numbers.
            if "Cannot destructure" in message or "destructure" in message.lower():
                return True
            if str(err.get("extensions", {}).get("class", "")) == "FAILURE" and len(errors) == 1:
                return True
            if PayPalFlow._dict_contains_card_field(err.get("errorData")):
                return True
        return False

    @staticmethod
    def _has_signup_error_message(errors: list[dict], message: str) -> bool:
        return any(str(err.get("message") or "") == message for err in errors or [])

    def _signup_with_card_retry(self, token: str, signup_url: str):
        """Retry SignUpNewMember with a fresh generated Visa/MasterCard on card errors."""
        self.state.euat_token = ""
        last_errors: list[dict] = []
        last_access_token = ""

        for attempt in range(1, self.max_card_attempts + 1):
            logger.info(
                "Step 3: Creating account (SignUpNewMember), card attempt {}/{}: {}",
                attempt,
                self.max_card_attempts,
                self._masked_card_number(),
            )
            signup_result = self._send_signup_attempt(token, signup_url)
            success, errors = self._consume_signup_result(signup_result)
            if success:
                return

            last_errors = errors
            access_token = self._find_access_token(errors)
            if access_token:
                last_access_token = access_token

            if self._has_signup_error_message(errors, "ACCOUNT_ALREADY_EXISTS"):
                if last_access_token:
                    self.state.euat_token = last_access_token
                    logger.warning(
                        "Signup returned ACCOUNT_ALREADY_EXISTS after a previous "
                        "response already issued an access token. Reusing that "
                        "token and continuing instead of re-submitting signup."
                    )
                    return
                raise RuntimeError(
                    "Signup failed: ACCOUNT_ALREADY_EXISTS and no prior access "
                    "token is available for this session."
                )

            if self._is_card_related_signup_error(errors):
                if access_token:
                    self.state.euat_token = access_token
                    logger.warning(
                        "Card/addCard failed but PayPal returned an access token. "
                        "The member account is already created at this point, so "
                        "re-sending SignUpNewMember with a new card would produce "
                        "ACCOUNT_ALREADY_EXISTS. Continuing with the returned token."
                    )
                    return

                if attempt >= self.max_card_attempts:
                    raise RuntimeError(
                        "Signup failed: card was rejected after "
                        f"{self.max_card_attempts} attempts"
                    )

                logger.warning(
                    "Card rejected by signup/addCard. Generating a fresh BR debit "
                    "card (oaipay BIN 414709/516292 + Luhn) and retrying..."
                )
                self.card = generate_card()
                logger.info(
                    "New generated card for retry: {} exp={}",
                    self._masked_card_number(),
                    self.card.expiry,
                )
                continue

            if access_token:
                self.state.euat_token = access_token
                logger.info("Got access token from signup error response")
                return

            break

        raise RuntimeError(
            "Signup failed: no usable access token obtained. "
            f"Last errors: {json.dumps(sanitize_for_log(last_errors), ensure_ascii=False)[:1000]}"
        )

    def _follow_modxo_action_redirect(self, resp, referer: str):
        """Follow Next server-action redirects emitted by ModXO.

        PayPal's server action may return a normal Location header or an
        x-action-redirect header such as "/?...;push". In the latter case the
        path is relative to the /pay app, not the site root.
        """
        redirect_url = resp.headers.get("Location") or resp.headers.get("x-action-redirect") or ""
        if not redirect_url:
            return resp
        redirect_url = redirect_url.split(";", 1)[0]
        if redirect_url.startswith("/?"):
            redirect_url = f"https://www.paypal.com/pay{redirect_url}"
        elif redirect_url.startswith("/"):
            redirect_url = f"https://www.paypal.com{redirect_url}"
        logger.info(f"Following ModXO action redirect: {redirect_url[:140]}...")
        return self.session.get(
            redirect_url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": referer,
                "Upgrade-Insecure-Requests": "1",
            },
        )

    def _phase1_risk_controls(self):
        """Send device fingerprints, Tealeaf data, analytics."""
        logger.info("--- Phase 1: Risk control signals ---")

        # Device fingerprint (p1, p2, w endpoints)
        send_device_fingerprint(self.session, self.ba_token)

        # Tealeaf initial data
        page_url = f"https://www.paypal.com/pay?ssrt={self.state.ssrt}&token={self.ba_token}&ul=1"
        send_tealeaf_data(self.session, page_url)

        # Analytics
        send_analytics_ts(self.session, "main:xo:modxo:login", self.ba_token, country=self._ensure_protocol().code)
        send_observability_emit(self.session, self.ba_token)

        logger.info("Risk control signals sent")

    def _phase2_create_account(self):
        """Submit 'Create Account' action to get to the signup page."""
        logger.info("--- Phase 2: Create account flow ---")

        self.state.ec_token = ""
        self.state.signup_url = ""
        self.state.signup_context_ready = False
        self.state.content_hash = ""
        self.state.content_identifier = ""
        resp = None
        modxo_error = ""
        # Browser trace (2026-07-04): ModXO is a Next server-action flow.
        # First click "Pay with Card", then submit an email/createAccount
        # action, whose RSC payload returns onboardingRedirectUrl.
        pay_url = (
            f"https://www.paypal.com/pay/?ssrt={self.state.ssrt}"
            f"&token={self.ba_token}&ul=1&ctxId={self.state.ctx_id}"
            f"&country.x={self._ensure_protocol().country_x}"
        )
        try:
            if not self.state.show_create_account_action_id or not self.state.create_user_action_id:
                raise RuntimeError("missing dynamic ModXO Next-Action ids")

            logger.info("Submitting browser-like Pay_With_Card server action...")
            pay_with_card_url = f"{pay_url}&paypal_client_cfci=modxo_vaulted_not_recurring-Pay_With_Card"
            mp = curl_cffi.CurlMime()
            mp.addpart(name="_1_ctxId", data=self.state.ctx_id)
            mp.addpart(name="_1_formName", data="createAccountAction")
            mp.addpart(name="0", data='["$K1"]')
            pay_resp = self.session.post(
                pay_with_card_url,
                multipart=mp,
                headers={
                    "Accept": "text/x-component",
                    "Origin": "https://www.paypal.com",
                    "Referer": pay_url,
                    "Next-Action": self.state.show_create_account_action_id,
                },
            )
            mp.close()
            if pay_resp.status_code in (301, 302, 303, 307, 308) or pay_resp.headers.get("x-action-redirect"):
                self._follow_modxo_action_redirect(pay_resp, pay_url)

            logger.info("Submitting browser-like Continue_To_Payment server action...")
            continue_url = f"{pay_url}&paypal_client_cfci=modxo_vaulted_not_recurring-Continue_To_Payment"
            mp2 = curl_cffi.CurlMime()
            mp2.addpart(name="_1_ctxId", data=self.state.ctx_id)
            mp2.addpart(name="_1_token", data=self.ba_token)
            mp2.addpart(name="_1_login_email", data=self.user.email)
            mp2.addpart(name="_1_formName", data="createAccount")
            mp2.addpart(name="0", data=f'["$K1",{{"emailSubmitTime":{int(time.time() * 1000)}}}]')
            rsc_resp = self.session.post(
                continue_url,
                multipart=mp2,
                headers={
                    "Accept": "text/x-component",
                    "Origin": "https://www.paypal.com",
                    "Referer": pay_with_card_url,
                    "Next-Action": self.state.create_user_action_id,
                },
            )
            mp2.close()
            onboarding_url = self._extract_onboarding_redirect(rsc_resp.text)
            logger.info(f"ModXO Continue_To_Payment status={rsc_resp.status_code} body_len={len(rsc_resp.text)} onboarding_url={'found' if onboarding_url else 'NOT FOUND'}")
            if not onboarding_url and rsc_resp.text:
                snippet = rsc_resp.text.replace('\n', ' ')[:500]
                logger.info(f"RSC response snippet: {snippet}")
            if onboarding_url:
                logger.info(f"Onboarding redirect URL: {onboarding_url[:140]}...")
                resp = self.session.get(
                    onboarding_url,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Referer": pay_url,
                        "Upgrade-Insecure-Requests": "1",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "same-origin",
                        "Sec-Fetch-User": "?1",
                    },
                )
        except Exception as e:
            modxo_error = str(e)
            logger.warning(f"Browser-like ModXO server-action path failed: {e}")

        if resp is None:
            # Fallback for older deployments that still accept a compact form.
            base_url = (
                f"https://www.paypal.com/pay?ssrt={self.state.ssrt}"
                f"&token={self.ba_token}&ul=1"
                f"&paypal_client_cfci=modxo_vaulted_not_recurring-Pay_With_Card"
            )

            form_data = {
                "ctxId": self.state.ctx_id,
                "formName": "createAccountAction",
                "fn_sync_data": build_fn_sync_data(self.ba_token),
            }

            resp = self.session.post(base_url, data=form_data, headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://www.paypal.com",
                "Referer": f"https://www.paypal.com/pay?ssrt={self.state.ssrt}&token={self.ba_token}&ul=1",
            })

        resp = self._follow_paypal_redirects(
            resp,
            stage="Phase 2 create-account transition",
            referer=pay_url,
        )
        logger.info(f"Phase 2 final URL: {str(getattr(resp, 'url', ''))[:200]}")
        logger.info(f"Phase 2 final status: {getattr(resp, 'status_code', 'N/A')}, body_len={len(getattr(resp, 'text', ''))}")
        self.state.ec_token = self._extract_ec_token(resp)
        try:
            ec_token = self._require_ec_token("Phase 2 create-account transition")
        except RuntimeError as exc:
            if modxo_error:
                raise RuntimeError(f"{exc}; ModXO path failed first: {modxo_error}") from exc
            raise
        logger.info("EC Token: {}", sanitize_for_log({"ec_token": ec_token})["ec_token"])

        # The real browser next loads checkoutweb/weasley.  This request is not
        # just cosmetic: it sets checkout cookies (for example l7_az/x-pp-s),
        # exposes the current content hash, and matches the Referer/context
        # expected by the following GraphQL mutations.
        if self.state.ec_token:
            signup_url = self._build_signup_url()
            self.state.signup_url = signup_url
            logger.info(f"Loading checkout signup app: {signup_url}")
            signup_resp = self.session.get(
                signup_url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": str(resp.url),
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-User": "?1",
                    "Priority": "u=0, i",
                },
            )
            signup_resp = self._follow_paypal_redirects(
                signup_resp,
                stage="Phase 2 checkout signup",
                referer=str(resp.url),
            )
            self.state.signup_url = str(signup_resp.url)
            logger.info(
                "Checkout signup app loaded: {} bytes={}",
                signup_resp.status_code,
                len(signup_resp.content),
            )
            self._validate_signup_response(signup_resp)
            initial_data = self._extract_window_initial_data(signup_resp.text)
            content_hash = initial_data.get("contentHash")
            if content_hash:
                self.state.content_hash = content_hash
                logger.info(f"Content hash: {self.state.content_hash}")
            proto = self._ensure_protocol()
            content_identifier = self._extract_content_identifier(
                signup_resp.text,
                proto.code,
                proto.content_lang,
            )
            if content_hash and content_identifier.endswith(":compliance.signupTerms") and content_hash not in content_identifier:
                content_identifier = f"{proto.code}:{proto.content_lang}:{content_hash}:compliance.signupTerms"
            elif content_identifier == f"{proto.code}:{proto.content_lang}:compliance.signupTerms":
                raise RuntimeError(
                    "Phase 2 checkout signup: dynamic signup terms identifier is missing"
                )
            self.state.content_identifier = content_identifier
            logger.info(f"Content identifier: {self.state.content_identifier}")

        # Send Tealeaf for new page
        send_tealeaf_data(
            self.session,
            self.state.signup_url if self.state.signup_url else str(resp.url),
        )
        send_observability_emit(self.session, self.ba_token)

        if self.state.ec_token:
            # Browser trace sends signup-page Weasley logs and EC-token risk
            # beacons before phone/card submission.  Missing these correlates
            # with opaque OAS_ERROR/createMemberAccount buckets.
            send_weasley_log(
                self.session,
                self.state.ec_token,
                self.state.signup_url,
                [
                    "weasley_client_eligibility_check_success",
                    "WEASLEY_PAGE_INTERACTIVE_FPTI",
                    "WEASLEY_PREPARE_BILLING_PAGE_FPTI",
                    "weasley_payment_request_api_available",
                ],
                country=self._ensure_protocol().code,
                lang=self._ensure_protocol().lang,
            )
            send_device_fingerprint(
                self.session,
                self.state.ec_token,
                app_id="CHECKOUTUINODEWEB_ONBOARDING_LITE",
                referer=self.state.signup_url,
                wrapped=True,
            )

        # Send the initial GraphQL queries
        logger.info("Sending checkout session GraphQL queries...")
        try:
            self.session.graphql(
                "DeferredFeature",
                DEFERRED_FEATURE_QUERY,
                {
                    "channel": "WEB",
                    "countryCodeAsString": self.address.country,
                    "integrationType": "XoSignupAuth",
                    "isBaslAsString": "false",
                    "isForcedGuest": "false",
                    "token": ec_token,
                },
            )
        except Exception as e:
            logger.warning(f"DeferredFeature failed: {e}")

        checkout_result = self.session.graphql(
            "CheckoutSessionDataQuery",
            CHECKOUT_SESSION_DATA_QUERY,
            {"token": ec_token},
        )
        self._require_checkout_session(checkout_result)
        self.state.signup_context_ready = True

        try:
            self.session.graphql(
                "GriffinMetadataQuery",
                GRIFFIN_METADATA_QUERY,
                {
                    "countryCode": self.address.country,
                    "languageCode": self.lang,
                    "shippingCountryCode": self.address.country,
                },
            )
        except Exception as e:
            logger.warning(f"GriffinMetadataQuery failed: {e}")

        try:
            self.session.graphql(
                "SupportedFundingSourcesQuery",
                SUPPORTED_FUNDING_SOURCES_QUERY,
                {
                    "token": ec_token,
                    "userCountry": self.address.country,
                },
            )
        except Exception as e:
            logger.warning(f"SupportedFundingSourcesQuery failed: {e}")

        try:
            address_result = self.session.graphql(
                "AddressAutocompleteFromPostalCodeQuery",
                ADDRESS_AUTOCOMPLETE_FROM_POSTAL_CODE_QUERY,
                {
                    "country": self.address.country,
                    "postalCode": self.address.postal_code,
                    "token": ec_token,
                },
            )
            result_obj = address_result[0] if isinstance(address_result, list) else address_result
            normalized = result_obj.get("data", {}).get("addressNormalization") or {}
            if normalized:
                logger.info(
                    "Address normalized: {}, {}, {} {}",
                    normalized.get("line1"),
                    normalized.get("line2"),
                    normalized.get("city"),
                    normalized.get("state"),
                )
                self.address.street = normalized.get("line1") or self.address.street
                self.address.district = normalized.get("line2") or self.address.district
                self.address.city = normalized.get("city") or self.address.city
                self.address.state = normalized.get("state") or self.address.state
                self.address.postal_code = normalized.get("postalCode") or self.address.postal_code
        except Exception as e:
            logger.warning(f"AddressAutocompleteFromPostalCodeQuery failed: {e}")

    def _phase3_signup_and_2fa(self):
        """Submit the signup form and trigger 2FA SMS.

        Actual flow discovered from traffic capture:
        1. InitiateRiskBasedTwoFactorPhoneConfirmationMutation → sends SMS, returns authId + challengeId
        2. ConfirmRiskBasedTwoFactorPhoneConfirmationMutation → verifies OTP pin with authId + challengeId
        3. SignUpNewMemberMutation → creates account with all user data + card + address
        """
        logger.info("--- Phase 3: Signup form + 2FA ---")

        token = self._require_signup_context("Phase 3 signup")
        signup_url = self.state.signup_url

        # Send Tealeaf to simulate form interaction
        send_tealeaf_data(self.session, signup_url)

        # Step 1/2: Send SMS and confirm OTP. If the OTP is wrong, the
        # operator can either retry a code for the same phone or enter a new
        # phone number to trigger a fresh challenge.
        self._confirm_phone_with_retry(token, signup_url)

        # Step 3: Sign up new member with all user data. If PayPal rejects the
        # card at addCard/validate.fi/cardNumber, fetch a new generated
        # Visa/MasterCard and submit SignUpNewMember again.
        self._signup_with_card_retry(token, signup_url)

        if not self.state.euat_token:
            raise RuntimeError(
                "Signup failed: no access token obtained. "
                "Cannot proceed to authorization without authentication."
            )

        self.session.client.cookies.set(
            "AV894Kt2TSumQQrJwe-8mzmyREO", self.state.euat_token,
            domain=".paypal.com",
        )

        # Send analytics for signup completion
        send_analytics_ts(
            self.session,
            "main:billing:hagrid:billingwithoutpurchase:member:review",
            self.ba_token,
            ec_token=self.state.ec_token,
            user_id=self.state.user_id,
            country=self._ensure_protocol().code,
        )

    def _phase4_authorize(self) -> dict:
        """Send the final authorize mutation to approve the billing agreement."""
        logger.info("--- Phase 4: Final authorization ---")

        billing_agreement_id = self._require_signup_context("Phase 4 authorize")
        if not self.state.euat_token:
            raise RuntimeError("Phase 4 authorize: authenticated member context is missing")

        hermes_base_url = (
            f"https://www.paypal.com/webapps/hermes?"
            f"ssrt={self.state.ssrt}&ul=1&modxo_redirect_reason=guest_user"
            f"&locale.x={self._ensure_protocol().locale_x}&country.x={self._ensure_protocol().country_x}"
            f"&ba_token={self.ba_token}&token={self.state.ec_token}"
            f"&rcache=1&cookieBannerVariant=hidden&fromSignupLite=true"
            f"&fallback=1&reason=Q0FSRF9HRU5FUklDX0VSUk9S"
        )
        hermes_contingency_url = (
            f"https://www.paypal.com/webapps/hermes?"
            f"ssrt={self.state.ssrt}&ul=1&modxo_redirect_reason=guest_user"
            f"&locale.x={self._ensure_protocol().locale_x}&country.x={self._ensure_protocol().country_x}"
            f"&ba_token={self.ba_token}&token={self.state.ec_token}"
            f"&rcache=1&cookieBannerVariant=hidden&fromSignupLite=true"
            f"&addFIContingency=noretry&redirectToHermes=true"
            f"&fallback=1&reason=Q0FSRF9HRU5FUklDX0VSUk9S"
        )
        review_referer = f"{hermes_base_url}&billingLite=1"
        review_url = f"{review_referer}#/billingweb/review"

        # Browser trace shows that Hagrid/Hermes is actually loaded before the
        # authorize mutation. This GET binds the EUAT/cookies to a buyer
        # context; without it GraphQL authorize can return BUYER_NOT_SET.
        try:
            logger.info("Loading Hermes/Hagrid review context...")
            base_headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Referer": self.state.signup_url,
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
            }
            first_review = self.session.get(hermes_contingency_url, headers=base_headers)
            self._follow_paypal_redirects(
                first_review,
                stage="Phase 4 Hermes contingency",
                referer=self.state.signup_url,
            )

            review_resp = self.session.get(hermes_base_url, headers=base_headers)
            review_resp = self._follow_paypal_redirects(
                review_resp,
                stage="Phase 4 Hermes review",
                referer=hermes_contingency_url,
            )
            logger.info(
                "Hermes/Hagrid review loaded: {} bytes={}",
                review_resp.status_code,
                len(review_resp.content),
            )
            if not self.state.user_id:
                # The server-rendered Hagrid page often contains party_id/cust.
                user_match = re.search(r'(?:party_id|cust|userId)["=:]+([A-Z0-9]{8,20})', review_resp.text)
                if user_match:
                    self.state.user_id = user_match.group(1)
                    logger.info(f"User ID from Hermes page: {self.state.user_id}")
        except Exception as e:
            raise RuntimeError(f"Phase 4 Hermes/Hagrid context failed: {e}") from e

        # Send Tealeaf for the review page
        send_tealeaf_data(self.session, review_url)

        # The critical authorize mutation
        logger.info(
            "Authorizing billing agreement: {}",
            sanitize_for_log({"billingAgreementId": billing_agreement_id})["billingAgreementId"],
        )

        def send_authorize():
            return self.session.graphql(
                "authorize",
                AUTHORIZE_BILLING_MUTATION,
                {
                    "billingAgreementId": billing_agreement_id,
                    "fundingPreference": {
                        "balancePreference": "OPT_OUT",
                    },
                    "legalAgreements": {},
                },
                extra_headers={
                    "Referer": review_referer,
                    "X-App-Name": "checkoutuinodeweb",
                    "PayPal-Client-Context": None,
                    "PayPal-Client-Metadata-Id": self.state.paypal_client_metadata_id,
                    "X-Country": None,
                    "X-Locale": None,
                },
                batched=True,
                endpoint="https://www.paypal.com/graphql/",
            )

        result = send_authorize()
        if self._has_buyer_not_set(result):
            logger.warning("authorize returned BUYER_NOT_SET; reloading billingLite review context and retrying once...")
            try:
                self.session.get(
                    review_referer,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Referer": hermes_base_url,
                        "Upgrade-Insecure-Requests": "1",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "same-origin",
                        "Sec-Fetch-User": "?1",
                    },
                )
                time.sleep(1)
            except Exception as e:
                logger.warning(f"Reloading billingLite review context failed: {e}")
            result = send_authorize()

        logger.info(
            "Authorization result (sanitized): {}",
            json.dumps(sanitize_for_log(result), ensure_ascii=False, indent=2)[:1000],
        )

        # Extract return URL and user ID from response
        try:
            result_obj = result[0] if isinstance(result, list) else result
            billing_data = result_obj.get("data", {}).get("billing", {})
            auth_data = billing_data.get("authorize") if isinstance(billing_data, dict) else None
            if not isinstance(auth_data, dict):
                errors = result_obj.get("errors") if isinstance(result_obj, dict) else None
                logger.error(
                    "Authorization failed: authorize is empty. Errors: {}",
                    json.dumps(sanitize_for_log(errors or []), ensure_ascii=False, indent=2),
                )
                return {
                    "status": "error",
                    "error": "authorize returned empty result",
                    "raw_response": result,
                }
            self.state.return_url = auth_data["returnURL"]["href"]
            self.state.user_id = auth_data["buyer"]["userId"]
            ba_token_resp = auth_data["billingAgreementToken"]

            logger.success(
                "Billing Agreement Token: {}",
                sanitize_for_log({"billingAgreementToken": ba_token_resp})["billingAgreementToken"],
            )
            logger.success(f"Payment Action: {auth_data['paymentAction']}")
            logger.success(f"Buyer User ID: {self.state.user_id}")
            logger.success("Return URL: <redacted>")

            final_redirect_url = ""
            try:
                logger.info("Following merchant return URL...")
                return_resp = self.session.get(
                    self.state.return_url,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Referer": review_url,
                        "Upgrade-Insecure-Requests": "1",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "cross-site",
                        "Sec-Fetch-User": "?1",
                    },
                )
                for _ in range(8):
                    if return_resp.status_code not in (301, 302, 303, 307, 308):
                        break
                    location = return_resp.headers.get("Location", "")
                    if not location:
                        break
                    final_redirect_url = urllib.parse.urljoin(str(return_resp.url), location)
                    return_resp = self.session.get(
                        final_redirect_url,
                        headers={
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Referer": str(return_resp.url),
                            "Upgrade-Insecure-Requests": "1",
                            "Sec-Fetch-Dest": "document",
                            "Sec-Fetch-Mode": "navigate",
                            "Sec-Fetch-Site": "cross-site",
                            "Sec-Fetch-User": "?1",
                        },
                    )
                if not final_redirect_url:
                    final_redirect_url = str(return_resp.url)
                logger.success("Final merchant URL: <redacted>")
            except Exception as e:
                logger.warning(f"Following merchant return URL failed: {e}")

            # Send final analytics
            send_analytics_ts(
                self.session,
                "main:billing:hagrid:billingwithoutpurchase:member:submitButtonFullEvent",
                self.ba_token,
                ec_token=self.state.ec_token,
                user_id=self.state.user_id,
                event="cl",
                country=self._ensure_protocol().code,
            )

            return self._attach_b_layer({
                "status": "success",
                "ba_token": ba_token_resp,
                "ec_token": self.state.ec_token,
                "user_id": self.state.user_id,
                "return_url": self.state.return_url,
                "final_redirect_url": final_redirect_url,
                "payment_action": auth_data["paymentAction"],
            })
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Failed to parse authorization response: {e}")
            return {
                "status": "error",
                "error": str(e),
                "raw_response": result,
            }

    def _session_cookie_snapshot(self) -> list[dict[str, object]]:
        cookies = []
        try:
            for cookie in self.session.client.cookies.jar:
                cookies.append({
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "secure": bool(cookie.secure),
                })
        except Exception as exc:
            logger.warning("Unable to snapshot PayPal session cookies: {}", exc)
        return cookies

    def _attach_b_layer(self, result: dict) -> dict:
        try:
            if getattr(self.state, "return_url", "") and not result.get("return_url"):
                result["return_url"] = self.state.return_url
            result["session_cookies"] = self._session_cookie_snapshot()
            result["b_layer"] = build_b_layer_evidence(result)
            result["protocol_mode"] = "http_only_full_protocol"
            result["region"] = self._ensure_protocol().code
            result["protocol"] = self._ensure_protocol().summary()
        except Exception as exc:
            result.setdefault("b_layer_error", str(exc))
        return result
