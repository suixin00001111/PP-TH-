"""Thailand local profile generator for pure-HTTP BA protocol.

No remote profile API. Names/addresses/postal codes are local pools.
"""
from __future__ import annotations

import random
import string
from paypal.models import UserInfo, CardInfo, BillingAddress, generate_card as _gen_card


TH_FIRST_NAMES = [
    "Somchai", "Somsak", "Somsri", "Anan", "Arthit", "Nattapong", "Kittipong",
    "Pichai", "Wichai", "Chaiwat", "Prasert", "Surachai", "Thanakorn", "Apichat",
    "Nattaya", "Siriporn", "Suda", "Malee", "Pornthip", "Wanida", "Kanya",
    "Ratchanee", "Patcharee", "Supaporn", "Naree", "Anchalee", "Pimchanok",
    "Kanokwan", "Chonticha", "Waranya", "Thanaporn", "Natcha", "Ploy",
]

TH_LAST_NAMES = [
    "Srisawat", "Saetang", "Chaiyo", "Wongsa", "Thongdee", "Rattana",
    "Phanich", "Suksamran", "Boonmee", "Jaidee", "Kaewmanee", "Siriwan",
    "Chanthara", "Prasert", "Wongsawat", "Boonsong", "Sutham", "Phetchaburi",
    "Nakhon", "Rattanapong", "Chaiyaphum", "Sombun", "Thavorn", "Phong",
]

# province_code, city, districts, postals
TH_LOCATIONS = [
    {"state": "BKK", "city": "Bangkok", "districts": ["Pathum Wan", "Watthana", "Bang Rak", "Sathon", "Khlong Toei", "Phra Nakhon"], "postals": ["10330", "10110", "10500", "10120", "10110", "10200"]},
    {"state": "BKK", "city": "Bangkok", "districts": ["Chatuchak", "Lat Phrao", "Bang Kapi", "Huai Khwang", "Din Daeng"], "postals": ["10900", "10230", "10240", "10310", "10400"]},
    {"state": "CNX", "city": "Chiang Mai", "districts": ["Mueang Chiang Mai", "Hang Dong", "San Sai", "Mae Rim"], "postals": ["50200", "50230", "50210", "50180"]},
    {"state": "CBI", "city": "Chon Buri", "districts": ["Bang Lamung", "Si Racha", "Mueang Chon Buri"], "postals": ["20150", "20230", "20000"]},
    {"state": "PKE", "city": "Phuket", "districts": ["Mueang Phuket", "Kathu", "Thalang"], "postals": ["83000", "83120", "83110"]},
    {"state": "NMA", "city": "Nakhon Ratchasima", "districts": ["Mueang Nakhon Ratchasima", "Pak Chong"], "postals": ["30000", "30130"]},
    {"state": "KKN", "city": "Khon Kaen", "districts": ["Mueang Khon Kaen", "Ban Phai"], "postals": ["40000", "40110"]},
    {"state": "SKN", "city": "Songkhla", "districts": ["Hat Yai", "Mueang Songkhla"], "postals": ["90110", "90000"]},
    {"state": "NPT", "city": "Nonthaburi", "districts": ["Mueang Nonthaburi", "Bang Bua Thong", "Pak Kret"], "postals": ["11000", "11110", "11120"]},
    {"state": "SPK", "city": "Samut Prakan", "districts": ["Mueang Samut Prakan", "Bang Phli", "Phra Pradaeng"], "postals": ["10270", "10540", "10130"]},
]

TH_STREETS = [
    "Sukhumvit Road", "Phahonyothin Road", "Ratchadaphisek Road", "Rama IV Road",
    "Silom Road", "Sathorn Road", "Lat Phrao Road", "Phetchaburi Road",
    "Charoen Krung Road", "Wireless Road", "Asok Montri Road", "Thong Lo Road",
    "Nimmanahaeminda Road", "Chang Klan Road", "Beach Road", "Thep Kasattri Road",
    "Mittraphap Road", "Maliwan Road", "Kanchanavanich Road", "Tiwanon Road",
]


def generate_password(length: int = 12) -> str:
    upper = random.choice(string.ascii_uppercase)
    lower = random.choice(string.ascii_lowercase)
    digit = random.choice(string.digits)
    special = random.choice("!@#$%")
    rest = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(max(4, length - 4)))
    chars = list(upper + lower + digit + special + rest)
    random.shuffle(chars)
    return "".join(chars)


def generate_dob() -> str:
    # adults 22-45
    year = random.randint(1981, 2003)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{day:02d}/{month:02d}/{year}"


def generate_email(first: str, last: str) -> str:
    num = random.randint(10, 9999)
    clean_first = "".join(ch for ch in first.lower() if ch.isalpha()) or "user"
    clean_last = "".join(ch for ch in last.lower() if ch.isalpha()) or "th"
    domain = random.choice(["gmail.com", "outlook.com", "yahoo.com", "hotmail.com"])
    return f"{clean_first}.{clean_last}{num}@{domain}"


def normalize_thailand_phone(phone: str = "") -> tuple[str, str, str]:
    """Return (e164, local, country_code)."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits.startswith("66"):
        local = digits[2:]
    elif digits.startswith("0") and len(digits) == 10:
        local = digits[1:]
    else:
        local = digits
    if not local:
        # random Thai mobile: 6/8/9 + 8 digits
        lead = random.choice(["6", "8", "9"])
        local = lead + "".join(str(random.randint(0, 9)) for _ in range(8))
    if not re_fullmatch_th(local):
        raise ValueError("手机号必须是泰国手机格式：+66 + 9 位（6/8/9 开头）")
    e164 = f"+66{local}"
    return e164, local, "+66"


def re_fullmatch_th(local: str) -> bool:
    return bool(local) and local[0] in "689" and local.isdigit() and len(local) == 9


def generate_address() -> BillingAddress:
    loc = random.choice(TH_LOCATIONS)
    district = random.choice(loc["districts"])
    postal = random.choice(loc["postals"])
    street = random.choice(TH_STREETS)
    house = str(random.randint(12, 999))
    return BillingAddress(
        street=street,
        house_number=house,
        district=district,
        city=loc["city"],
        state=loc["state"],
        postal_code=postal,
        country="TH",
    )


def generate_user(phone: str = "") -> UserInfo:
    first = random.choice(TH_FIRST_NAMES)
    last = random.choice(TH_LAST_NAMES)
    e164, local, cc = normalize_thailand_phone(phone)
    return UserInfo(
        first_name=first,
        last_name=last,
        email=generate_email(first, last),
        phone=e164,
        phone_local=local,
        phone_country_code=cc,
        password=generate_password(),
        dob=generate_dob(),
        national_id="",
        cpf="",
    )


def generate_card() -> CardInfo:
    return _gen_card()


def generate_oaipy_user(phone: str = "") -> UserInfo:
    return generate_user(phone=phone)


def generate_oaipy_card() -> CardInfo:
    return generate_card()


def generate_oaipy_address() -> BillingAddress:
    return generate_address()


def generate_oaipy_profile(phone: str = "") -> dict:
    return {
        "user": generate_user(phone=phone),
        "card": generate_card(),
        "address": generate_address(),
    }


def generate_random_email() -> str:
    first = random.choice(TH_FIRST_NAMES)
    last = random.choice(TH_LAST_NAMES)
    return generate_email(first, last)


if __name__ == "__main__":
    p = generate_oaipy_profile(phone="+66812345678")
    u, c, a = p["user"], p["card"], p["address"]
    print(u.first_name, u.last_name, u.phone, u.email)
    print(c.number, c.expiry)
    print(a.street, a.house_number, a.district, a.city, a.state, a.postal_code, a.country)
