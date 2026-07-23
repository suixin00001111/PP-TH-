"""Country-specific profile generation via open-source Faker locales.

Protocol flow: Thailand is the *reference state machine* only.
Profile identity (name / address / phone / optional CPF) always follows the
selected country protocol — never Thai identity data for non-TH runs.

Data source: Faker (https://github.com/joke2k/faker, MIT License)
Each country maps to a Faker locale provider so names/cities/streets come from
community-maintained open data, not hand-invented lists.
"""
from __future__ import annotations

import random
import string
from functools import lru_cache

from faker import Faker

from paypal.models import UserInfo, CardInfo, BillingAddress, generate_card as _gen_card
from paypal.regions import normalize_phone, normalize_region, get_region, DEFAULT_REGION

# Country ISO2 -> Faker locale (open-source providers)
# https://faker.readthedocs.io/en/master/locales.html
FAKER_LOCALE_BY_COUNTRY: dict[str, str] = {
    "TH": "th_TH",
    "JP": "ja_JP",
    "US": "en_US",
    "GB": "en_GB",
    "BR": "pt_BR",
    "MX": "es_MX",
    "ID": "id_ID",
    "MY": "ms_MY",  # may fall back
    "SG": "en_US",  # no dedicated SG; use en with SG cities below
    "PH": "en_PH",  # may fall back
    "VN": "vi_VN",  # may fall back
    "KR": "ko_KR",
    "HK": "zh_TW",  # closest maintained CJK latin/traditional mix; address post-fixed HK
    "TW": "zh_TW",
    "CN": "zh_CN",
    "AU": "en_AU",
    "NZ": "en_NZ",
    "CA": "en_CA",
    "DE": "de_DE",
    "FR": "fr_FR",
    "ES": "es_ES",
    "IT": "it_IT",
    "NL": "nl_NL",
    "SE": "sv_SE",
    "PL": "pl_PL",
    "PT": "pt_PT",
    "IE": "en_IE",  # may fall back en_GB
    "CH": "de_CH",
    "AT": "de_AT",
    "BE": "nl_BE",  # may fall back nl_NL / fr_FR
    "DK": "da_DK",
    "NO": "no_NO",
    "FI": "fi_FI",
    "IN": "en_IN",
    "AE": "ar_AA",  # generic Arabic if available
    "SA": "ar_SA",  # may fall back ar_AA
    "IL": "he_IL",
    "TR": "tr_TR",
    "RU": "ru_RU",
    "ZA": "en_US",  # en_ZA may exist
    "AR": "es_AR",
    "CL": "es_CL",
    "CO": "es_CO",
    "PE": "es_PE",  # may fall back es_ES
}

# Fallback chain when primary locale missing in installed Faker
FAKER_FALLBACKS: dict[str, list[str]] = {
    "ms_MY": ["en_US"],
    "en_PH": ["en_US"],
    "vi_VN": ["en_US"],
    "en_IE": ["en_GB", "en_US"],
    "nl_BE": ["nl_NL", "fr_FR", "en_US"],
    "no_NO": ["nb_NO", "en_US"],
    "ar_SA": ["ar_AA", "en_US"],
    "ar_AA": ["en_US"],
    "es_PE": ["es_ES", "es_MX", "en_US"],
    "es_CL": ["es_ES", "es_MX", "en_US"],
    "es_CO": ["es_ES", "es_MX", "en_US"],
    "es_AR": ["es_ES", "es_MX", "en_US"],
    "zh_TW": ["zh_CN", "en_US"],
    "zh_CN": ["en_US"],
    "he_IL": ["en_US"],
    "id_ID": ["en_US"],
    "th_TH": ["en_US"],
    "ja_JP": ["en_US"],
    "ko_KR": ["en_US"],
    "pt_BR": ["pt_PT", "en_US"],
    "pt_PT": ["en_US"],
}

# When Faker locale is shared (e.g. SG->en_US), force realistic capital/city labels
CITY_OVERRIDE: dict[str, list[tuple[str, str, str]]] = {
    # state, city, postal
    "SG": [("SG", "Singapore", "018956"), ("SG", "Singapore", "238801")],
    "HK": [("HK", "Hong Kong", "999077")],
    "AE": [("DU", "Dubai", "00000"), ("AZ", "Abu Dhabi", "00000")],
    "SA": [("01", "Riyadh", "12211"), ("02", "Jeddah", "21442")],
    "ZA": [("GP", "Johannesburg", "2196"), ("WC", "Cape Town", "8001")],
}


def generate_cpf() -> str:
    nums = [random.randint(0, 9) for _ in range(9)]
    s = sum((10 - i) * nums[i] for i in range(9))
    d1 = (s * 10) % 11 % 10
    nums.append(d1)
    s = sum((11 - i) * nums[i] for i in range(10))
    d2 = (s * 10) % 11 % 10
    nums.append(d2)
    return "".join(str(n) for n in nums)


@lru_cache(maxsize=64)
def _faker_for_locale(locale: str) -> Faker:
    tried = [locale] + FAKER_FALLBACKS.get(locale, []) + ["en_US"]
    last_err: Exception | None = None
    for loc in tried:
        try:
            return Faker(loc)
        except Exception as exc:  # locale not installed / invalid
            last_err = exc
            continue
    # Absolute last resort
    return Faker("en_US")


def _faker_for_country(code: str) -> tuple[Faker, str]:
    code = normalize_region(code)
    primary = FAKER_LOCALE_BY_COUNTRY.get(code, "en_US")
    fake = _faker_for_locale(primary)
    return fake, primary


def _latin_name(fake: Faker) -> tuple[str, str]:
    """Build form-safe names from Faker locale data (open-source).

    Prefer the selected locale's person provider. Non-Latin scripts are
    romanized via Unidecode so PayPal form fields stay ASCII-friendly, while
    still originating from that country's Faker dataset (not hand-invented).
    """
    try:
        from unidecode import unidecode
    except Exception:  # pragma: no cover
        def unidecode(s: str) -> str:  # type: ignore
            return s

    first = str(getattr(fake, "first_name", lambda: "Alex")())
    last = str(getattr(fake, "last_name", lambda: "Lee")())
    first = unidecode(first)
    last = unidecode(last)
    first = "".join(ch for ch in first if ch.isalpha() or ch in "-' ")[:40].strip()
    last = "".join(ch for ch in last if ch.isalpha() or ch in "-' ")[:40].strip()
    if not first or not last:
        en = _faker_for_locale("en_US")
        first = unidecode(en.first_name())
        last = unidecode(en.last_name())
        first = "".join(ch for ch in first if ch.isalpha() or ch in "-' ")[:40].strip() or "Alex"
        last = "".join(ch for ch in last if ch.isalpha() or ch in "-' ")[:40].strip() or "Lee"
    return first.split()[0], last.split()[-1]


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
    fake, _loc = _faker_for_country(code)

    if code in CITY_OVERRIDE:
        state, city, postal = random.choice(CITY_OVERRIDE[code])
        district = city
    else:
        try:
            city = str(fake.city())
        except Exception:
            city = "Capital"
        try:
            state = str(getattr(fake, "state_abbr", lambda: getattr(fake, "state", lambda: "ST")())())
        except Exception:
            try:
                state = str(fake.state())[:12]
            except Exception:
                state = "ST"
        try:
            postal = str(fake.postcode())
        except Exception:
            postal = f"{random.randint(10000, 99999)}"
        try:
            district = str(getattr(fake, "city_suffix", lambda: city)())
            if not district or district == city:
                district = city
        except Exception:
            district = city

    try:
        street = str(fake.street_name())
    except Exception:
        try:
            street = str(fake.street_address()).split(",")[0]
        except Exception:
            street = "Main Street"

    # house number
    if code == "JP":
        house = f"{random.randint(1, 28)}-{random.randint(1, 20)}-{random.randint(1, 15)}"
    else:
        try:
            bldg = str(fake.building_number())
            house = "".join(ch for ch in bldg if ch.isdigit() or ch in "-/")[:12] or str(random.randint(1, 999))
        except Exception:
            house = str(random.randint(1, 999))

    # Keep country code authoritative (selected protocol)
    return BillingAddress(
        street=street[:80],
        house_number=house,
        district=str(district)[:60],
        city=str(city)[:60],
        state=str(state)[:30],
        postal_code="".join(ch for ch in str(postal) if ch.isalnum() or ch in "- ")[:16] or f"{random.randint(10000,99999)}",
        country=code,
    )


def generate_user(phone: str = "", country: str = DEFAULT_REGION) -> UserInfo:
    code = normalize_region(country)
    fake, _loc = _faker_for_country(code)
    first, last = _latin_name(fake)
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
        "meta": {
            "country": code,
            "faker_locale": FAKER_LOCALE_BY_COUNTRY.get(code, "en_US"),
            "data_source": "Faker (https://github.com/joke2k/faker, MIT)",
            "protocol_reference": "TH state machine",
        },
    }


def generate_random_email(country: str = DEFAULT_REGION) -> str:
    code = normalize_region(country)
    fake, _ = _faker_for_country(code)
    first, last = _latin_name(fake)
    return generate_email(first, last)
