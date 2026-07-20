"""Local profile generator for pure-HTTP BA protocol (multi-country).

Profile pools follow the Thailand package structure; non-TH countries use
romanized / English-style local templates with the selected country code.
"""
from __future__ import annotations

import random
import string

from paypal.models import UserInfo, CardInfo, BillingAddress, generate_card as _gen_card
from paypal.regions import normalize_phone, normalize_region, get_region, DEFAULT_REGION


def generate_cpf() -> str:
    """Generate a valid random CPF (digits only, 11)."""
    nums = [random.randint(0, 9) for _ in range(9)]
    s = sum((10 - i) * nums[i] for i in range(9))
    d1 = (s * 10) % 11 % 10
    nums.append(d1)
    s = sum((11 - i) * nums[i] for i in range(10))
    d2 = (s * 10) % 11 % 10
    nums.append(d2)
    return "".join(str(n) for n in nums)



TH_FIRST = ["Somchai", "Somsak", "Anan", "Nattapong", "Siriporn", "Suda", "Pimchanok", "Kanokwan", "Waranya", "Natcha"]
TH_LAST = ["Srisawat", "Saetang", "Wongsa", "Boonmee", "Jaidee", "Nakhon", "Sutham", "Phong"]
TH_LOC = [
    {"state": "BKK", "city": "Bangkok", "districts": ["Pathum Wan", "Watthana", "Bang Rak"], "postals": ["10330", "10110", "10500"]},
    {"state": "CNX", "city": "Chiang Mai", "districts": ["Mueang Chiang Mai", "Hang Dong"], "postals": ["50200", "50230"]},
]
TH_STREET = ["Sukhumvit Road", "Silom Road", "Sathorn Road", "Lat Phrao Road", "Beach Road"]

JP_FIRST = ["Haruto", "Yuki", "Ren", "Sora", "Hina", "Sakura", "Mio", "Akari", "Takumi", "Kenji"]
JP_LAST = ["Sato", "Suzuki", "Tanaka", "Watanabe", "Ito", "Yamamoto", "Nakamura", "Kobayashi"]
JP_LOC = [
    {"state": "13", "city": "Tokyo", "districts": ["Shibuya", "Shinjuku", "Minato"], "postals": ["1500002", "1600022", "1060032"]},
    {"state": "27", "city": "Osaka", "districts": ["Kita", "Chuo"], "postals": ["5300001", "5410041"]},
]
JP_STREET = ["Meiji-dori", "Omotesando", "Midosuji", "Chuo-dori", "Dotonbori"]

EN_FIRST = ["James", "John", "Robert", "Michael", "David", "Emily", "Sarah", "Anna", "Olivia", "Sophia", "Daniel", "Lucas"]
EN_LAST = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Wilson", "Moore", "Taylor"]
GENERIC_STREET = ["Main Street", "High Street", "Park Avenue", "Oak Road", "Maple Drive", "Church Road", "Station Road"]

# Minimal city templates by country code
CITY_MAP = {
    "US": [("CA", "Los Angeles", "90001"), ("NY", "New York", "10001"), ("TX", "Houston", "77001")],
    "GB": [("ENG", "London", "SW1A1AA"), ("ENG", "Manchester", "M11AE"), ("SCT", "Edinburgh", "EH11YZ")],
    "BR": [("SP", "Sao Paulo", "01001000"), ("RJ", "Rio de Janeiro", "20040020")],
    "MX": [("CMX", "Mexico City", "01000"), ("JAL", "Guadalajara", "44100")],
    "ID": [("JK", "Jakarta", "10110"), ("BA", "Denpasar", "80111")],
    "MY": [("KUL", "Kuala Lumpur", "50000"), ("PNG", "George Town", "10000")],
    "SG": [("SG", "Singapore", "018956")],
    "PH": [("NCR", "Manila", "1000"), ("CEB", "Cebu", "6000")],
    "VN": [("HN", "Hanoi", "100000"), ("SG", "Ho Chi Minh City", "700000")],
    "KR": [("11", "Seoul", "04524"), ("26", "Busan", "48058")],
    "HK": [("HK", "Hong Kong", "999077")],
    "TW": [("TPE", "Taipei", "100"), ("KHH", "Kaohsiung", "800")],
    "CN": [("BJ", "Beijing", "100000"), ("SH", "Shanghai", "200000")],
    "AU": [("NSW", "Sydney", "2000"), ("VIC", "Melbourne", "3000")],
    "NZ": [("AUK", "Auckland", "1010"), ("WGN", "Wellington", "6011")],
    "CA": [("ON", "Toronto", "M5H2N2"), ("BC", "Vancouver", "V6B1A1")],
    "DE": [("BE", "Berlin", "10115"), ("BY", "Munich", "80331")],
    "FR": [("IDF", "Paris", "75001"), ("ARA", "Lyon", "69001")],
    "ES": [("MD", "Madrid", "28001"), ("CT", "Barcelona", "08001")],
    "IT": [("RM", "Rome", "00100"), ("MI", "Milan", "20100")],
    "NL": [("NH", "Amsterdam", "1011"), ("ZH", "Rotterdam", "3011")],
    "SE": [("AB", "Stockholm", "11120")],
    "PL": [("MZ", "Warsaw", "00-001")],
    "PT": [("11", "Lisbon", "1000-001")],
    "IE": [("D", "Dublin", "D01"), ("C", "Cork", "T12")],
    "CH": [("ZH", "Zurich", "8001")],
    "AT": [("9", "Vienna", "1010")],
    "BE": [("BRU", "Brussels", "1000")],
    "DK": [("84", "Copenhagen", "1050")],
    "NO": [("03", "Oslo", "0001")],
    "FI": [("18", "Helsinki", "00100")],
    "IN": [("DL", "New Delhi", "110001"), ("MH", "Mumbai", "400001")],
    "AE": [("DU", "Dubai", "00000")],
    "SA": [("01", "Riyadh", "11564")],
    "IL": [("TA", "Tel Aviv", "61000")],
    "TR": [("34", "Istanbul", "34000")],
    "RU": [("MOW", "Moscow", "101000")],
    "ZA": [("GP", "Johannesburg", "2000")],
    "AR": [("C", "Buenos Aires", "1000")],
    "CL": [("RM", "Santiago", "8320000")],
    "CO": [("DC", "Bogota", "110111")],
    "PE": [("LIM", "Lima", "15001")],
}


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
    year = random.randint(1981, 2003)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{day:02d}/{month:02d}/{year}"


def generate_email(first: str, last: str) -> str:
    num = random.randint(10, 9999)
    clean_first = "".join(ch for ch in first.lower() if ch.isalpha()) or "user"
    clean_last = "".join(ch for ch in last.lower() if ch.isalpha()) or "mail"
    domain = random.choice(["gmail.com", "outlook.com", "yahoo.com", "hotmail.com"])
    return f"{clean_first}.{clean_last}{num}@{domain}"


def normalize_thailand_phone(phone: str = "") -> tuple[str, str, str]:
    return normalize_phone("TH", phone)


def re_fullmatch_th(local: str) -> bool:
    return bool(local) and local[0] in "689" and local.isdigit() and len(local) == 9


def generate_address(country: str = DEFAULT_REGION) -> BillingAddress:
    code = normalize_region(country)
    if code == "TH":
        loc = random.choice(TH_LOC)
        return BillingAddress(
            street=random.choice(TH_STREET),
            house_number=str(random.randint(12, 999)),
            district=random.choice(loc["districts"]),
            city=loc["city"],
            state=loc["state"],
            postal_code=random.choice(loc["postals"]),
            country="TH",
        )
    if code == "JP":
        loc = random.choice(JP_LOC)
        return BillingAddress(
            street=random.choice(JP_STREET),
            house_number=f"{random.randint(1, 28)}-{random.randint(1, 20)}-{random.randint(1, 15)}",
            district=random.choice(loc["districts"]),
            city=loc["city"],
            state=loc["state"],
            postal_code=random.choice(loc["postals"]),
            country="JP",
        )
    cities = CITY_MAP.get(code) or [("ST", "Capital", "10000")]
    state, city, postal = random.choice(cities)
    return BillingAddress(
        street=random.choice(GENERIC_STREET),
        house_number=str(random.randint(1, 999)),
        district=city,
        city=city,
        state=state,
        postal_code=postal,
        country=code,
    )


def generate_user(phone: str = "", country: str = DEFAULT_REGION) -> UserInfo:
    code = normalize_region(country)
    if code == "TH":
        first, last = random.choice(TH_FIRST), random.choice(TH_LAST)
    elif code == "JP":
        first, last = random.choice(JP_FIRST), random.choice(JP_LAST)
    else:
        first, last = random.choice(EN_FIRST), random.choice(EN_LAST)
    e164, local, cc = normalize_phone(code, phone)
    region = get_region(code)
    cpf = ""
    national_id = ""
    if region.send_identity_document and region.identity_type == "CPF":
        cpf = generate_cpf()
        national_id = cpf
    return UserInfo(
        first_name=first,
        last_name=last,
        email=generate_email(first, last),
        phone=e164,
        phone_local=local,
        phone_country_code=cc,
        password=generate_password(),
        dob=generate_dob(),
        national_id=national_id,
        cpf=cpf,
    )


def generate_card() -> CardInfo:
    return _gen_card()


def generate_oaipy_user(phone: str = "", country: str = DEFAULT_REGION) -> UserInfo:
    return generate_user(phone=phone, country=country)


def generate_oaipy_card() -> CardInfo:
    return generate_card()


def generate_oaipy_address(country: str = DEFAULT_REGION) -> BillingAddress:
    return generate_address(country=country)


def generate_oaipy_profile(phone: str = "", country: str = DEFAULT_REGION) -> dict:
    code = normalize_region(country)
    return {
        "user": generate_user(phone=phone, country=code),
        "card": generate_card(),
        "address": generate_address(country=code),
    }


def generate_random_email(country: str = DEFAULT_REGION) -> str:
    code = normalize_region(country)
    if code == "TH":
        first, last = random.choice(TH_FIRST), random.choice(TH_LAST)
    elif code == "JP":
        first, last = random.choice(JP_FIRST), random.choice(JP_LAST)
    else:
        first, last = random.choice(EN_FIRST), random.choice(EN_LAST)
    return generate_email(first, last)
