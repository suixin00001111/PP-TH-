from dataclasses import dataclass, field
from typing import Any, Optional
import random
import string
import time
import uuid
import calendar


@dataclass
class UserInfo:
    first_name: str
    last_name: str
    email: str
    phone: str
    phone_local: str
    phone_country_code: str
    password: str
    dob: str  # DD/MM/YYYY
    national_id: str = ""
    cpf: str = ""  # used for BR identity document


@dataclass
class CardInfo:
    number: str
    expiry: str  # MM/YYYY
    cvv: str
    card_type: str = "CREDIT"


@dataclass
class BillingAddress:
    street: str
    house_number: str
    district: str
    city: str
    state: str
    postal_code: str
    country: str = "TH"


@dataclass
class SessionState:
    ba_token: str = ""
    region: str = "TH"
    ec_token: str = ""
    ssrt: str = ""
    ctx_id: str = ""
    nsid: str = ""
    d_id: str = ""
    user_id: str = ""
    datadome_cookie: str = ""
    datadome_clientid: str = ""
    tltsid: str = ""
    tltdid: str = ""
    tealeaf_serial_number: int = 0
    tealeaf_page_id: str = field(default_factory=lambda: f"P.{uuid.uuid4().hex[:24].upper()}")
    tealeaf_tab_id: str = field(default_factory=lambda: f"Y{random.randint(100, 999)}")
    tealeaf_start_time_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    paypal_client_metadata_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    euat_token: str = ""
    return_url: str = ""
    content_hash: str = ""
    content_identifier: str = ""
    content_manifest_url: str = ""
    content_manifest_key: str = ""
    signup_url: str = ""
    signup_context_ready: bool = False
    paypal_captcha_solved: bool = False
    show_create_account_action_id: str = ""
    create_user_action_id: str = ""
    submit_public_credential_action_id: str = ""
    fetch_device_fingerprint_action_id: str = ""
    modxo_country_action_id: str = ""
    modxo_country_action_bound: str = ""
    modxo_country_selected: bool = False
    modxo_pay_page_url: str = ""
    passkey_challenge: str = ""
    rp_id: str = ""
    login_phone_country_code: str = ""
    modxo_deployment_id: str = ""
    signup_fallback_reason: str = ""
    mtr_channel: str = ""
    mtr_client_metadata_id: str = ""
    mtr_api_key: str = ""
    mtr_is_qa: bool = False
    mtr_dfp_script_url: str = ""
    mtr_get_status: int = 0
    mtr_post_status: int = 0
    mtr_request_id: str = ""
    mtr_sealed_result: str = ""
    mtr_runtime_source: str = ""
    mtr_visitor_token: str = ""
    mtr_completed: bool = False
    mtr_completed_cmid: str = ""
    mtr_browser_result: dict[str, object] = field(default_factory=dict)
    captcha_synthetic_used: bool = False
    datadome_header_injected: bool = False
    fingerprint_source: str = ""
    roxy_browser: dict[str, object] = field(default_factory=dict)
    datadome_browser_solved: bool = False
    datadome_browser_result: dict[str, object] = field(default_factory=dict)
    risk_signals_runtime_source: str = ""
    risk_signals_browser_result: dict[str, object] = field(default_factory=dict)
    browser_profile: dict[str, object] = field(default_factory=dict)
    screen: dict[str, object] = field(default_factory=dict)
    viewport: dict[str, object] = field(default_factory=dict)
    device_fingerprint: dict[str, object] = field(default_factory=dict)
    pxp_guid: str = field(default_factory=lambda: uuid.uuid4().hex)
    page_start_time_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    fpti_calc: str = field(default_factory=lambda: uuid.uuid4().hex[:13])
    datadog_session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    datadog_view_ids: dict[str, object] = field(default_factory=dict)

    def update_from_cookies(self, cookies: dict[str, str]) -> None:
        if "nsid" in cookies:
            self.nsid = cookies["nsid"]
        if "d_id" in cookies:
            self.d_id = cookies["d_id"]
        if "datadome" in cookies:
            self.datadome_cookie = cookies["datadome"]
        if "TLTSID" in cookies:
            self.tltsid = cookies["TLTSID"]
        if "TLTDID" in cookies:
            self.tltdid = cookies["TLTDID"]
        euat_key = "AV894Kt2TSumQQrJwe-8mzmyREO"
        if euat_key in cookies:
            self.euat_token = cookies[euat_key]



def generate_random_email() -> str:
    chars = string.ascii_lowercase + string.digits
    user = "".join(random.choice(chars) for _ in range(12))
    return f"{user}@gmail.com"


def generate_eteid() -> list:
    return [
        random.randint(-10000000000, 20000000000),
        random.randint(-10000000000, 20000000000),
        random.randint(-10000000000, 20000000000),
        random.randint(-10000000000, 20000000000),
        random.randint(-10000000000, 20000000000),
        random.randint(-10000000000, 20000000000),
        None,
        None,
    ]


def _luhn_checksum(partial: str) -> int:
    digits = [int(d) for d in partial]
    for i in range(len(digits) - 1, -1, -2):
        digits[i] *= 2
        if digits[i] > 9:
            digits[i] -= 9
    total = sum(digits)
    return (10 - (total % 10)) % 10


_FALLBACK_CARD_PREFIXES = [
    ("4", "VISA"),
    ("51", "MASTER_CARD"),
    ("52", "MASTER_CARD"),
    ("53", "MASTER_CARD"),
    ("54", "MASTER_CARD"),
    ("55", "MASTER_CARD"),
]


def generate_card(proxy_url: str | None = None, country: str | None = None) -> CardInfo:
    del proxy_url
    try:
        from paypal.country_profiles import generate_card_number
        number, brand = generate_card_number(country)
    except Exception:
        prefix, brand = random.choice(_FALLBACK_CARD_PREFIXES)
        remaining = 16 - len(prefix) - 1
        body = prefix + "".join(str(random.randint(0, 9)) for _ in range(remaining))
        number = body + str(_luhn_checksum(body))
    month = random.randint(1, 12)
    year = random.randint(2027, 2031)
    expiry = f"{month:02d}/{year}"
    cvv = f"{random.randint(0, 999):03d}"
    # brand kept only for future issuer mapping; CardInfo is number-focused
    del brand
    return CardInfo(number=number, expiry=expiry, cvv=cvv, card_type="CREDIT")


def generate_user(phone: str = "", country: str = "TH") -> UserInfo:
    """Multi-country user generation via oaipy_data (Faker locales)."""
    from paypal.oaipy_data import generate_user as _gen
    return _gen(phone=phone, country=country)
