from dataclasses import dataclass, field
from typing import Optional
import random
import string
import time
import uuid


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
    # Thailand signup does not require Thailandian CPF. Keep optional for protocol compat.
    national_id: str = ""
    cpf: str = ""  # legacy alias; left empty for TH


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
    ec_token: str = ""
    ssrt: str = ""
    ctx_id: str = ""
    nsid: str = ""
    d_id: str = ""
    user_id: str = ""
    datadome_cookie: str = ""
    tltsid: str = ""
    tltdid: str = ""
    paypal_client_metadata_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    euat_token: str = ""
    return_url: str = ""
    content_hash: str = ""
    content_identifier: str = ""
    signup_url: str = ""
    signup_context_ready: bool = False
    show_create_account_action_id: str = ""
    create_user_action_id: str = ""
    region: str = "TH"

    def update_from_cookies(self, cookies: dict):
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


def generate_card(proxy_url: str | None = None) -> CardInfo:
    del proxy_url  # unused; kept for BR call-site compatibility
    prefix, _issuer = random.choice(_FALLBACK_CARD_PREFIXES)
    remaining = 16 - len(prefix) - 1
    body = prefix + "".join(str(random.randint(0, 9)) for _ in range(remaining))
    check = _luhn_checksum(body)
    number = body + str(check)
    month = random.randint(1, 12)
    year = random.randint(2027, 2031)
    expiry = f"{month:02d}/{year}"
    cvv = f"{random.randint(0, 999):03d}"
    return CardInfo(number=number, expiry=expiry, cvv=cvv, card_type="CREDIT")
