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
import re
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

# Thailand: PayPal checkout expects coherent province/city/postal pairs.
# Faker th_TH often yields Thai-script streets and a bogus state "ST", which
# can collapse SignUpNewMember into opaque onboardAccount FAILURE.
_TH_LOCATIONS: list[dict[str, str]] = [
    {"state": "Bangkok", "city": "Bangkok", "district": "Pathum Wan", "postal": "10330"},
    {"state": "Bangkok", "city": "Bangkok", "district": "Watthana", "postal": "10110"},
    {"state": "Bangkok", "city": "Bangkok", "district": "Bang Rak", "postal": "10500"},
    {"state": "Bangkok", "city": "Bangkok", "district": "Chatuchak", "postal": "10900"},
    {"state": "Chiang Mai", "city": "Chiang Mai", "district": "Mueang", "postal": "50200"},
    {"state": "Chiang Mai", "city": "Chiang Mai", "district": "Hang Dong", "postal": "50230"},
    {"state": "Phuket", "city": "Phuket", "district": "Mueang", "postal": "83000"},
    {"state": "Phuket", "city": "Phuket", "district": "Kathu", "postal": "83120"},
    {"state": "Chon Buri", "city": "Pattaya", "district": "Bang Lamung", "postal": "20150"},
    {"state": "Chon Buri", "city": "Chon Buri", "district": "Si Racha", "postal": "20110"},
    {"state": "Nonthaburi", "city": "Nonthaburi", "district": "Mueang", "postal": "11000"},
    {"state": "Samut Prakan", "city": "Samut Prakan", "district": "Mueang", "postal": "10270"},
    {"state": "Khon Kaen", "city": "Khon Kaen", "district": "Mueang", "postal": "40000"},
    {"state": "Nakhon Ratchasima", "city": "Nakhon Ratchasima", "district": "Mueang", "postal": "30000"},
    {"state": "Songkhla", "city": "Hat Yai", "district": "Hat Yai", "postal": "90110"},
]

_TH_STREETS = [
    "Sukhumvit Road",
    "Phahonyothin Road",
    "Ratchadamri Road",
    "Silom Road",
    "Sathorn Road",
    "Rama IV Road",
    "Lat Phrao Road",
    "Phetchaburi Road",
    "Charoen Krung Road",
    "Wireless Road",
    "Asok Montri Road",
    "Thong Lo Road",
]

_JP_LOCATIONS = [
    {"state": "Tokyo", "city": "Shibuya", "district": "Shibuya", "postal": "150-0002", "street": "Meiji Dori"},
    {"state": "Tokyo", "city": "Shinjuku", "district": "Shinjuku", "postal": "160-0022", "street": "Yasukuni Dori"},
    {"state": "Tokyo", "city": "Minato", "district": "Roppongi", "postal": "106-0032", "street": "Roppongi Dori"},
    {"state": "Osaka", "city": "Osaka", "district": "Chuo", "postal": "540-0002", "street": "Mido Suji"},
    {"state": "Osaka", "city": "Osaka", "district": "Kita", "postal": "530-0001", "street": "Umeda Street"},
    {"state": "Kyoto", "city": "Kyoto", "district": "Nakagyo", "postal": "604-8005", "street": "Kawaramachi Street"},
    {"state": "Kanagawa", "city": "Yokohama", "district": "Naka", "postal": "231-0023", "street": "Bashamichi"},
    {"state": "Aichi", "city": "Nagoya", "district": "Naka", "postal": "460-0008", "street": "Sakae Street"},
]

_KR_LOCATIONS = [
    {"state": "Seoul", "city": "Seoul", "district": "Gangnam-gu", "postal": "06236", "street": "Teheran-ro"},
    {"state": "Seoul", "city": "Seoul", "district": "Jongno-gu", "postal": "03154", "street": "Jongno"},
    {"state": "Seoul", "city": "Seoul", "district": "Mapo-gu", "postal": "04038", "street": "Hongik-ro"},
    {"state": "Busan", "city": "Busan", "district": "Haeundae-gu", "postal": "48094", "street": "Haeundaehaebyeon-ro"},
    {"state": "Incheon", "city": "Incheon", "district": "Namdong-gu", "postal": "21556", "street": "Artcenter-daero"},
    {"state": "Daegu", "city": "Daegu", "district": "Jung-gu", "postal": "41911", "street": "Dongseong-ro"},
    {"state": "Gyeonggi", "city": "Suwon", "district": "Yeongtong-gu", "postal": "16517", "street": "Gwanggyojungang-ro"},
]


_CN_LOCATIONS = [
    {"state": "Shanghai", "city": "Shanghai", "district": "Huangpu", "postal": "200001", "street": "Nanjing Road"},
    {"state": "Shanghai", "city": "Shanghai", "district": "Xuhui", "postal": "200030", "street": "Huaihai Road"},
    {"state": "Beijing", "city": "Beijing", "district": "Chaoyang", "postal": "100020", "street": "Jianguo Road"},
    {"state": "Beijing", "city": "Beijing", "district": "Dongcheng", "postal": "100006", "street": "Wangfujing Street"},
    {"state": "Guangdong", "city": "Guangzhou", "district": "Tianhe", "postal": "510620", "street": "Tianhe Road"},
    {"state": "Guangdong", "city": "Shenzhen", "district": "Nanshan", "postal": "518052", "street": "Houhai Avenue"},
    {"state": "Zhejiang", "city": "Hangzhou", "district": "Xihu", "postal": "310012", "street": "Wenyi Road"},
]

_HK_LOCATIONS = [
    {"state": "HK", "city": "Hong Kong", "district": "Central", "postal": "999077", "street": "Queens Road Central"},
    {"state": "HK", "city": "Hong Kong", "district": "Tsim Sha Tsui", "postal": "999077", "street": "Nathan Road"},
    {"state": "HK", "city": "Hong Kong", "district": "Causeway Bay", "postal": "999077", "street": "Hennessy Road"},
    {"state": "HK", "city": "Hong Kong", "district": "Mong Kok", "postal": "999077", "street": "Argyle Street"},
    {"state": "HK", "city": "Hong Kong", "district": "Wan Chai", "postal": "999077", "street": "Johnston Road"},
]

_VN_LOCATIONS = [
    {"state": "HN", "city": "Hanoi", "district": "Hoan Kiem", "postal": "100000", "street": "Hang Bai"},
    {"state": "HN", "city": "Hanoi", "district": "Ba Dinh", "postal": "100000", "street": "Kim Ma"},
    {"state": "SG", "city": "Ho Chi Minh City", "district": "District 1", "postal": "700000", "street": "Nguyen Hue"},
    {"state": "SG", "city": "Ho Chi Minh City", "district": "District 3", "postal": "700000", "street": "Vo Van Tan"},
    {"state": "DN", "city": "Da Nang", "district": "Hai Chau", "postal": "550000", "street": "Bach Dang"},
    {"state": "HP", "city": "Hai Phong", "district": "Hong Bang", "postal": "180000", "street": "Dien Bien Phu"},
]


def _generate_curated_address(code: str, locations: list[dict[str, str]], house_style: str = "simple") -> BillingAddress:
    location = random.choice(locations)
    if house_style == "jp":
        house = f"{random.randint(1, 28)}-{random.randint(1, 20)}-{random.randint(1, 15)}"
    elif house_style == "kr":
        house = f"{random.randint(1, 999)}-{random.randint(1, 99)}"
    else:
        house = str(random.randint(1, 999))
    return BillingAddress(
        street=location["street"],
        house_number=house,
        district=location["district"],
        city=location["city"],
        state=location["state"],
        postal_code=location["postal"],
        country=code,
    )



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


# Curated Latin name pools for locales whose Faker output is native-script
# and becomes unreadable after Unidecode (not encoding corruption).
_LATIN_NAME_POOLS: dict[str, dict[str, list[str]]] = {
    "TH": {
        "first": [
            "Somchai", "Nattapong", "Anan", "Somsak", "Wichai", "Kittisak", "Pichai",
            "Thanawat", "Arthit", "Chaiwat", "Niran", "Prasert", "Supachai", "Warut",
            "Peerapat", "Ratchanon", "Panupong", "Theerapat", "Tanakorn", "Phakphum",
            "Siriporn", "Nattaya", "Malee", "Suda", "Pimchanok", "Kanokwan", "Orathai",
            "Warunee", "Chutima", "Apinya", "Naree", "Patcharin", "Ratchanok", "Sasithorn",
            "Thanyarat", "Kamonwan", "Anong", "Busaba", "Chanida", "Duangjai",
        ],
        "last": [
            "Saetang", "Chaiyo", "Wongchai", "Srisuk", "Boonmee", "Charoen", "Suksawat",
            "Rattanakul", "Phongphan", "Thongsuk", "Kittiwat", "Anuwat", "Jirawat",
            "Wongsawat", "Boonsong", "Sutham", "Phromma", "Ruengrit", "Kaewmanee",
            "Chanthara", "Siripong", "Phanich", "Thongdee", "Rattanapong", "Chaiyaphum",
            "Suwannaphum", "Prasertchai", "Intarachai", "Wongsa", "Saelee",
        ],
    },
    "JP": {
        "first": [
            "Haruto", "Yuto", "Sota", "Ren", "Hiroto", "Kaito", "Sora", "Riku",
            "Yamato", "Takumi", "Kenji", "Daiki", "Sho", "Naoki", "Yuji", "Kazuki",
            "Aoi", "Yui", "Hina", "Sakura", "Mio", "Rin", "Yuna", "Mei", "Saki",
            "Akari", "Nanami", "Miyu", "Koharu", "Himari",
        ],
        "last": [
            "Sato", "Suzuki", "Takahashi", "Tanaka", "Watanabe", "Ito", "Yamamoto",
            "Nakamura", "Kobayashi", "Kato", "Yoshida", "Yamada", "Sasaki", "Yamaguchi",
            "Matsumoto", "Inoue", "Kimura", "Hayashi", "Shimizu", "Yamazaki",
            "Mori", "Abe", "Ikeda", "Hashimoto", "Ishikawa",
        ],
    },
    "KR": {
        "first": [
            "Minjun", "Seojun", "Jihun", "Hyunwoo", "Donghyun", "Jaehyun", "Minho",
            "Sungmin", "Youngho", "Taeyang", "Jiwoo", "Hyejin", "Soyeon", "Minji",
            "Yuna", "Jiyoon", "Haeun", "Seoyeon", "Nari", "Eunji", "Kyungsoo",
            "Jisoo", "Harin", "Chaewon", "Yejin",
        ],
        "last": [
            "Kim", "Lee", "Park", "Choi", "Jung", "Kang", "Cho", "Yoon", "Jang",
            "Lim", "Han", "Oh", "Seo", "Shin", "Kwon", "Hwang", "Ahn", "Song",
            "Hong", "Jeon", "Yu", "Ko", "Moon", "Yang", "Bae",
        ],
    },
    "CN": {
        "first": [
            "Wei", "Ming", "Jun", "Hao", "Lei", "Tao", "Fang", "Yan", "Jing",
            "Xia", "Qiang", "Bo", "Yong", "Jie", "Xin", "Ting", "Li", "Na",
            "Mei", "Hua", "Chen", "Yu", "Lin", "Ping", "Rui",
        ],
        "last": [
            "Wang", "Li", "Zhang", "Liu", "Chen", "Yang", "Huang", "Zhao", "Wu",
            "Zhou", "Xu", "Sun", "Ma", "Zhu", "Hu", "Guo", "He", "Gao", "Lin",
            "Luo", "Zheng", "Liang", "Xie", "Song", "Tang",
        ],
    },
    "HK": {
        "first": [
            "Ka Ming", "Wing", "Chun", "Ho", "Man", "Yiu", "Siu", "Kin", "Wai",
            "Pui", "Tsz", "Hoi", "Lok", "Yat", "Chi", "Mei", "Yan", "Ling",
            "Ka Yi", "Wing Sze",
        ],
        "last": [
            "Chan", "Wong", "Cheung", "Lau", "Lee", "Ng", "Cheng", "Lam", "Leung",
            "Ho", "Yip", "Tsang", "Chow", "Mak", "Tang", "Fung", "Kwok", "Au",
            "Tam", "Siu",
        ],
    },
    "TW": {
        "first": [
            "Wei", "Chiahao", "Yuting", "Jiajun", "Yichen", "Zhiming", "Shufen",
            "Meiling", "Hsinyi", "Chenghan", "Peishan", "Chihhao", "Yating",
            "Kuanyu", "Anqi",
        ],
        "last": [
            "Chen", "Lin", "Huang", "Chang", "Lee", "Wang", "Wu", "Liu", "Tsai",
            "Yang", "Hsu", "Cheng", "Kuo", "Chiu", "Tseng", "Liao", "Hsieh",
            "Chou", "Yeh", "Hung",
        ],
    },
    "VN": {
        "first": [
            "Minh", "Anh", "Hung", "Dung", "Tuan", "Long", "Quang", "Nam", "Khoa",
            "Phuc", "Linh", "Trang", "Huong", "Nga", "Thao", "Mai", "Lan", "Hoa",
            "My", "Yen", "Hai", "Son", "Dat", "Kiet", "Bao",
        ],
        "last": [
            "Nguyen", "Tran", "Le", "Pham", "Hoang", "Huynh", "Phan", "Vu", "Vo",
            "Dang", "Bui", "Do", "Ho", "Ngo", "Duong", "Ly",
        ],
    },
}

_BAD_PLACEHOLDER_TEXT = {
    "", "st", "state", "n/a", "na", "none", "null", "ville", "city", "town",
    "capital", "center", "centre", "unknown", "test", "asdf",
}


def _title_name_part(value: str) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    parts: list[str] = []
    for token in text.replace("_", " ").split(" "):
        if not token:
            continue
        if "-" in token:
            parts.append("-".join(p[:1].upper() + p[1:].lower() if p else "" for p in token.split("-")))
        elif "'" in token:
            parts.append("'".join(p[:1].upper() + p[1:].lower() if p else "" for p in token.split("'")))
        else:
            parts.append(token[:1].upper() + token[1:].lower())
    return " ".join(parts)


def _name_quality_ok(value: str, *, kind: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    alpha = "".join(ch for ch in text if ch.isalpha())
    if len(alpha) < 2:
        return False
    vowels = sum(1 for ch in alpha.lower() if ch in "aeiouy")
    if len(alpha) >= 5 and vowels == 0:
        return False
    if len(alpha) >= 8 and vowels < 2:
        return False
    lower = alpha.lower()
    for i in range(len(lower) - 4):
        window = lower[i:i + 5]
        if sum(1 for ch in window if ch not in "aeiouy") >= 5:
            return False
    return True


def _pick_curated_name(code: str) -> tuple[str, str] | None:
    code = normalize_region(code)
    pool = _LATIN_NAME_POOLS.get(code)
    if not pool:
        return None
    first = _title_name_part(random.choice(pool["first"]))
    last = _title_name_part(random.choice(pool["last"]))
    if not first or not last:
        return None
    # Keep multi-part given names for HK only (common romanization style).
    if code == "HK" and " " in first:
        return first, last
    return first.split()[0], last.split()[-1]


def _latin_name(fake: Faker, country: str = DEFAULT_REGION) -> tuple[str, str]:
    """Build form-safe names with readable Latin output for CJK/Thai locales."""
    code = normalize_region(country)
    curated = _pick_curated_name(code)
    if curated is not None:
        return curated
    return _form_safe_pair(fake, country=code)


def _unidecode_text(value: str) -> str:
    try:
        from unidecode import unidecode
    except Exception:  # pragma: no cover
        def unidecode(s: str) -> str:  # type: ignore
            return s
    return unidecode(str(value or ""))


def _form_safe_text(value: str, *, fallback: str = "") -> str:
    """Romanize and keep PayPal form-safe printable ASCII text."""
    text = _unidecode_text(value)
    text = "".join(ch for ch in text if ch.isprintable() and ord(ch) < 128)
    text = " ".join(text.replace(",", " ").split()).strip(" -/'")
    cleaned = text[:80].strip()
    if cleaned.lower() in _BAD_PLACEHOLDER_TEXT:
        return fallback
    return cleaned or fallback


def _form_safe_pair(fake: Faker, country: str = DEFAULT_REGION) -> tuple[str, str]:
    code = normalize_region(country)

    def _clean_part(raw: str) -> str:
        text = _unidecode_text(raw)
        text = "".join(ch for ch in text if ch.isalpha() or ch in "-' ")[:40].strip()
        return _title_name_part(text)

    first = _clean_part(str(getattr(fake, "first_name", lambda: "Alex")()))
    last = _clean_part(str(getattr(fake, "last_name", lambda: "Lee")()))

    if not _name_quality_ok(first, kind="first") or not _name_quality_ok(last, kind="last"):
        curated = _pick_curated_name(code)
        if curated is not None:
            return curated
        en = _faker_for_locale("en_US")
        first = _clean_part(en.first_name()) or "Alex"
        last = _clean_part(en.last_name()) or "Lee"

    first_out = first.split()[0] if first else "Alex"
    last_out = last.split()[-1] if last else "Lee"
    if not _name_quality_ok(first_out, kind="first"):
        first_out = "Alex"
    if not _name_quality_ok(last_out, kind="last"):
        last_out = "Lee"
    return first_out, last_out


def _generate_th_address() -> BillingAddress:
    location = random.choice(_TH_LOCATIONS)
    street = random.choice(_TH_STREETS)
    house = str(random.randint(12, 999))
    if random.random() < 0.35:
        house = f"{house}/{random.randint(1, 20)}"
    return BillingAddress(
        street=street,
        house_number=house,
        district=location["district"],
        city=location["city"],
        state=location["state"],
        postal_code=location["postal"],
        country="TH",
    )


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


def generate_email(first: str, last: str, country: str = DEFAULT_REGION) -> str:
    clean_first = ''.join(ch for ch in str(first or '').lower() if ch.isalnum()) or 'user'
    clean_last = ''.join(ch for ch in str(last or '').lower() if ch.isalnum()) or 'mail'
    num = random.randint(10, 9999)
    try:
        from paypal.country_profiles import pick_email_domain
        domain = pick_email_domain(country)
    except Exception:
        domain = random.choice(['gmail.com', 'outlook.com', 'yahoo.com', 'hotmail.com'])
    return f'{clean_first}.{clean_last}{num}@{domain}'


def normalize_thailand_phone(phone: str = "") -> tuple[str, str, str]:
    return normalize_phone("TH", phone)


def re_fullmatch_th(local: str) -> bool:
    return bool(local) and local[0] in "689" and local.isdigit() and len(local) == 9


def generate_address(country: str = DEFAULT_REGION) -> BillingAddress:
    code = normalize_region(country)
    try:
        from paypal.country_profiles import generate_address_dict, ADDRESS_POOLS
        if code in ADDRESS_POOLS:
            data = generate_address_dict(code)
            return BillingAddress(
                street=data['street'],
                house_number=data['house_number'],
                district=data['district'],
                city=data['city'],
                state=data['state'],
                postal_code=data['postal_code'],
                country=code,
            )
    except Exception:
        pass
    if code == "TH":
        return _generate_th_address()
    if code == "JP":
        return _generate_curated_address("JP", _JP_LOCATIONS, house_style="jp")
    if code == "KR":
        return _generate_curated_address("KR", _KR_LOCATIONS, house_style="kr")
    if code == "VN":
        return _generate_curated_address("VN", _VN_LOCATIONS, house_style="simple")
    if code == "CN":
        return _generate_curated_address("CN", _CN_LOCATIONS, house_style="simple")
    if code == "HK":
        return _generate_curated_address("HK", _HK_LOCATIONS, house_style="simple")

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

    street = _form_safe_text(street, fallback="Main Street")
    district = _form_safe_text(str(district), fallback="Center")
    city = _form_safe_text(str(city), fallback="Capital")
    state = _form_safe_text(str(state), fallback=code)
    if not state or state.upper() in {"ST", "STATE", "N/A", "NA", "NONE"} or state.lower() in _BAD_PLACEHOLDER_TEXT:
        state = code
    if city.lower() in _BAD_PLACEHOLDER_TEXT:
        city = {
            "JP": "Tokyo",
            "KR": "Seoul",
            "CN": "Shanghai",
            "VN": "Ho Chi Minh City",
            "ID": "Jakarta",
            "NL": "Amsterdam",
        }.get(code, "Capital")
    if district.lower() in _BAD_PLACEHOLDER_TEXT:
        district = city
    if street.lower() in _BAD_PLACEHOLDER_TEXT or len("".join(ch for ch in street if ch.isalpha())) < 3:
        street = {
            "JP": random.choice(["Sakura Dori", "Ginza Street", "Omotesando"]),
            "KR": random.choice(["Teheran-ro", "Gangnam-daero", "Jongno"]),
            "CN": random.choice(["Nanjing Road", "Huaihai Road", "Zhongshan Road"]),
            "VN": random.choice(["Nguyen Hue", "Le Loi", "Tran Hung Dao"]),
        }.get(code, "Main Street")
    postal = "".join(ch for ch in str(postal) if ch.isalnum() or ch in "- ")[:16] or f"{random.randint(10000,99999)}"
    house = _form_safe_text(str(house), fallback=str(random.randint(1, 999))) or str(random.randint(1, 999))

    # Keep country code authoritative (selected protocol)
    return BillingAddress(
        street=street[:80],
        house_number=house[:12],
        district=district[:60],
        city=city[:60],
        state=state[:30],
        postal_code=postal,
        country=code,
    )


def generate_user(phone: str = "", country: str = DEFAULT_REGION) -> UserInfo:
    code = normalize_region(country)
    fake, _loc = _faker_for_country(code)
    first, last = _latin_name(fake, country=code)
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
        email=generate_email(first, last, country=code),
        phone=e164,
        phone_local=local,
        phone_country_code=cc,
        password=generate_password(),
        dob=generate_dob(),
        national_id=national_id,
        cpf=cpf,
    )


def generate_card(country: str = DEFAULT_REGION) -> CardInfo:
    code = normalize_region(country)
    try:
        return _gen_card(country=code)
    except TypeError:
        return _gen_card()


def generate_oaipy_user(phone: str = "", country: str = DEFAULT_REGION) -> UserInfo:
    return generate_user(phone=phone, country=country)


def generate_oaipy_card(country: str = DEFAULT_REGION) -> CardInfo:
    return generate_card(country=country)


def generate_oaipy_address(country: str = DEFAULT_REGION) -> BillingAddress:
    return generate_address(country=country)


def generate_oaipy_profile(phone: str = '', country: str = DEFAULT_REGION) -> dict:
    code = normalize_region(country)
    try:
        from paypal.country_profiles import content_manifest_hints, profile_depth
        content = content_manifest_hints(code)
        depth = profile_depth(code)
    except Exception:
        content = {'short_identifier': f'{code}:en:compliance.signupTerms', 'prefer_live_extract': True}
        depth = {'tier': 'template'}
    return {
        'user': generate_user(phone=phone, country=code),
        'card': generate_card(country=code),
        'address': generate_address(country=code),
        'meta': {
            'country': code,
            'faker_locale': FAKER_LOCALE_BY_COUNTRY.get(code, 'en_US'),
            'data_source': 'country_profiles + Faker + curated Latin name pools',
            'protocol_reference': 'TH state machine',
            'profile_depth': depth,
            'content': content,
        },
    }


def generate_random_email(country: str = DEFAULT_REGION) -> str:
    code = normalize_region(country)
    fake, _ = _faker_for_country(code)
    first, last = _latin_name(fake, country=code)
    return generate_email(first, last, country=code)

