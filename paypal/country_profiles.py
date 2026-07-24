"""Deep per-country profile data: phone / address / card BIN / content id.

Gold markets (TH/JP/US/BR/GB) carry the densest curated pools. Other supported
markets keep solid, coherent generators so protocol runs do not fall back to
generic Faker junk (wrong postal, placeholder streets, global card prefixes).

Live content hashes are still preferred at runtime; this module only supplies:
- short content identifiers (country:lang:compliance.signupTerms)
- optional known full hashes when observed from successful dumps
- phone/address/BIN pools for profile generation
"""
from __future__ import annotations

import random
import re
from typing import Any

# ---------------------------------------------------------------------------
# Phone rules
# ---------------------------------------------------------------------------

# local_len may be int or tuple(min, max). prefixes are national significant
# number starts *without* trunk 0.
PHONE_RULES: dict[str, dict[str, Any]] = {
    "TH": {"cc": "66", "local_len": 9, "prefixes": ("6", "8", "9"), "trunk_zero": True},
    "JP": {"cc": "81", "local_len": 10, "prefixes": ("70", "80", "90"), "trunk_zero": True},
    "US": {"cc": "1", "local_len": 10, "prefixes": ("201", "212", "213", "305", "310", "312", "415", "469", "512", "617", "650", "702", "713", "718", "786", "818", "832", "917", "949"), "trunk_zero": False, "nxx_not_start_0_1": True},
    "GB": {"cc": "44", "local_len": 10, "prefixes": ("7400", "7401", "7402", "7477", "7480", "7500", "7535", "7700", "7780", "7799", "7800", "7811", "7890"), "trunk_zero": True},
    "BR": {"cc": "55", "local_len": 11, "prefixes": ("119", "219", "319", "419", "479", "489", "519", "619", "719", "819", "859"), "trunk_zero": False},
    "KR": {"cc": "82", "local_len": 10, "prefixes": ("10", "11"), "trunk_zero": True},
    "TW": {"cc": "886", "local_len": 9, "prefixes": ("9",), "trunk_zero": True},
    "HK": {"cc": "852", "local_len": 8, "prefixes": ("5", "6", "9"), "trunk_zero": False},
    "SG": {"cc": "65", "local_len": 8, "prefixes": ("8", "9"), "trunk_zero": False},
    "VN": {"cc": "84", "local_len": 9, "prefixes": ("3", "5", "7", "8", "9"), "trunk_zero": True},
    "CN": {"cc": "86", "local_len": 11, "prefixes": ("130", "131", "132", "133", "135", "136", "137", "138", "139", "150", "151", "152", "155", "156", "157", "158", "159", "170", "176", "177", "178", "180", "181", "182", "183", "185", "186", "187", "188", "189"), "trunk_zero": False},
    "NL": {"cc": "31", "local_len": 9, "prefixes": ("6",), "trunk_zero": True},
    "MX": {"cc": "52", "local_len": 10, "prefixes": ("55", "33", "81", "222", "442", "664", "998"), "trunk_zero": False},
    "ID": {"cc": "62", "local_len": (10, 12), "prefixes": ("811", "812", "813", "814", "815", "816", "817", "818", "819", "821", "822", "823", "851", "852", "853", "855", "856", "857", "858"), "trunk_zero": True},
    "MY": {"cc": "60", "local_len": (9, 10), "prefixes": ("10", "11", "12", "13", "14", "16", "17", "18", "19"), "trunk_zero": True},
    "PH": {"cc": "63", "local_len": 10, "prefixes": ("905", "906", "907", "908", "909", "910", "912", "915", "916", "917", "918", "919", "920", "921", "922", "923", "926", "927", "928", "929", "930", "939"), "trunk_zero": True},
    "AU": {"cc": "61", "local_len": 9, "prefixes": ("4",), "trunk_zero": True},
    "NZ": {"cc": "64", "local_len": (8, 10), "prefixes": ("20", "21", "22", "27", "28", "29"), "trunk_zero": True},
    "CA": {"cc": "1", "local_len": 10, "prefixes": ("204", "236", "249", "250", "289", "306", "343", "365", "403", "416", "418", "437", "438", "450", "506", "514", "519", "548", "579", "581", "587", "604", "613", "639", "647", "672", "705", "709", "778", "780", "807", "819", "825", "867", "873", "902", "905"), "trunk_zero": False, "nxx_not_start_0_1": True},
    "DE": {"cc": "49", "local_len": (10, 11), "prefixes": ("151", "152", "157", "159", "160", "162", "163", "170", "171", "172", "173", "174", "175", "176", "177", "178", "179"), "trunk_zero": True},
    "FR": {"cc": "33", "local_len": 9, "prefixes": ("6", "7"), "trunk_zero": True},
    "ES": {"cc": "34", "local_len": 9, "prefixes": ("6", "7"), "trunk_zero": False},
    "IT": {"cc": "39", "local_len": 10, "prefixes": ("3",), "trunk_zero": False},
}


def _local_len_bounds(rule: dict[str, Any]) -> tuple[int, int]:
    raw = rule.get("local_len", 9)
    if isinstance(raw, (tuple, list)) and len(raw) == 2:
        return int(raw[0]), int(raw[1])
    n = int(raw)
    return n, n


def generate_local_phone(country: str) -> str:
    """Generate a national significant number (no leading +cc, no trunk 0)."""
    code = (country or "TH").strip().upper()
    rule = PHONE_RULES.get(code) or PHONE_RULES["TH"]
    lo, hi = _local_len_bounds(rule)
    prefixes = tuple(rule.get("prefixes") or ("9",))
    usable = [p for p in prefixes if lo <= len(str(p)) <= hi]
    if not usable:
        usable = [str(prefixes[0])[:lo]]
    prefix = str(random.choice(usable))
    target = random.randint(max(lo, len(prefix)), hi)
    remaining = target - len(prefix)
    body = []
    for i in range(remaining):
        if i == 0 and rule.get("nxx_not_start_0_1") and len(prefix) == 3:
            body.append(str(random.randint(2, 9)))
        else:
            body.append(str(random.randint(0, 9)))
    local = prefix + "".join(body)
    if code in {"US", "CA"} and len(local) == 10 and local[3:6] == "555":
        local = local[:3] + f"{random.randint(200, 989):03d}" + local[6:]
    return local


def validate_local_phone(country: str, local: str) -> bool:
    code = (country or "TH").strip().upper()
    rule = PHONE_RULES.get(code)
    digits = re.sub(r"\D", "", str(local or ""))
    if digits.startswith("0"):
        digits = digits[1:]
    if not rule:
        return 6 <= len(digits) <= 15 and digits.isdigit()
    lo, hi = _local_len_bounds(rule)
    if not (lo <= len(digits) <= hi and digits.isdigit()):
        return False
    prefixes = tuple(str(p) for p in (rule.get("prefixes") or ()))
    if prefixes and not any(digits.startswith(p) for p in prefixes):
        return False
    if rule.get("nxx_not_start_0_1") and len(digits) >= 6:
        if digits[3] in {"0", "1"}:
            return False
    return True


def e164_phone(country: str, local: str | None = None) -> tuple[str, str, str]:
    code = (country or "TH").strip().upper()
    rule = PHONE_RULES.get(code) or {"cc": "66"}
    cc = str(rule.get("cc") or "66")
    loc = re.sub(r"\D", "", str(local or "")) or generate_local_phone(code)
    if loc.startswith("0"):
        loc = loc[1:]
    if loc.startswith(cc) and len(loc) > len(cc) + 5:
        loc = loc[len(cc):]
    return f"+{cc}{loc}", loc, f"+{cc}"

# ---------------------------------------------------------------------------
# Card BINs (public IIN-style prefixes used for Luhn-valid synthetic cards)
# ---------------------------------------------------------------------------

# (bin_prefix, pan_length, brand)
CARD_BINS: dict[str, list[tuple[str, int, str]]] = {
    "TH": [
        ("454638", 16, "VISA"),
        ("540104", 16, "MASTER_CARD"),
        ("478200", 16, "VISA"),
        ("525636", 16, "MASTER_CARD"),
        ("455223", 16, "VISA"),
    ],
    "JP": [
        ("353011", 16, "JCB"),
        ("354100", 16, "JCB"),
        ("454118", 16, "VISA"),
        ("516366", 16, "MASTER_CARD"),
        ("356600", 16, "JCB"),
    ],
    "US": [
        ("414720", 16, "VISA"),
        ("424631", 16, "VISA"),
        ("518600", 16, "MASTER_CARD"),
        ("521729", 16, "MASTER_CARD"),
        ("601100", 16, "DISCOVER"),
    ],
    "BR": [
        ("414709", 16, "VISA"),
        ("516292", 16, "MASTER_CARD"),
        ("498408", 16, "VISA"),
        ("530034", 16, "MASTER_CARD"),
    ],
    "GB": [
        ("454313", 16, "VISA"),
        ("475127", 16, "VISA"),
        ("535522", 16, "MASTER_CARD"),
        ("557347", 16, "MASTER_CARD"),
    ],
    "KR": [
        ("356910", 16, "JCB"),
        ("456735", 16, "VISA"),
        ("536510", 16, "MASTER_CARD"),
    ],
    "TW": [
        ("356296", 16, "JCB"),
        ("428450", 16, "VISA"),
        ("515712", 16, "MASTER_CARD"),
    ],
    "HK": [
        ("454888", 16, "VISA"),
        ("542418", 16, "MASTER_CARD"),
        ("356835", 16, "JCB"),
    ],
    "SG": [
        ("455599", 16, "VISA"),
        ("526471", 16, "MASTER_CARD"),
        ("356895", 16, "JCB"),
    ],
    "VN": [
        ("970436", 16, "LOCAL"),
        ("970422", 16, "LOCAL"),
        ("428310", 16, "VISA"),
        ("530987", 16, "MASTER_CARD"),
    ],
    "CN": [
        ("622202", 16, "UNIONPAY"),
        ("621700", 16, "UNIONPAY"),
        ("625094", 16, "UNIONPAY"),
        ("458123", 16, "VISA"),
    ],
    "NL": [
        ("454617", 16, "VISA"),
        ("510039", 16, "MASTER_CARD"),
        ("552157", 16, "MASTER_CARD"),
    ],
    "MX": [
        ("415231", 16, "VISA"),
        ("547046", 16, "MASTER_CARD"),
        ("491566", 16, "VISA"),
    ],
    "ID": [
        ("461700", 16, "VISA"),
        ("526422", 16, "MASTER_CARD"),
        ("489503", 16, "VISA"),
    ],
    "MY": [
        ("453997", 16, "VISA"),
        ("543603", 16, "MASTER_CARD"),
    ],
    "PH": [
        ("421764", 16, "VISA"),
        ("548009", 16, "MASTER_CARD"),
    ],
    "AU": [
        ("456469", 16, "VISA"),
        ("521729", 16, "MASTER_CARD"),
        ("516361", 16, "MASTER_CARD"),
    ],
    "CA": [
        ("450003", 16, "VISA"),
        ("519123", 16, "MASTER_CARD"),
        ("552606", 16, "MASTER_CARD"),
    ],
    "DE": [
        ("490762", 16, "VISA"),
        ("518791", 16, "MASTER_CARD"),
        ("453997", 16, "VISA"),
    ],
    "FR": [
        ("497010", 16, "VISA"),
        ("513163", 16, "MASTER_CARD"),
        ("497355", 16, "VISA"),
    ],
    "ES": [
        ("454881", 16, "VISA"),
        ("557907", 16, "MASTER_CARD"),
    ],
    "IT": [
        ("453997", 16, "VISA"),
        ("530125", 16, "MASTER_CARD"),
    ],
    "NZ": [
        ("473633", 16, "VISA"),
        ("543388", 16, "MASTER_CARD"),
    ],
}

_FALLBACK_BINS: list[tuple[str, int, str]] = [
    ("4", 16, "VISA"),
    ("51", 16, "MASTER_CARD"),
    ("52", 16, "MASTER_CARD"),
    ("53", 16, "MASTER_CARD"),
    ("54", 16, "MASTER_CARD"),
    ("55", 16, "MASTER_CARD"),
]


def _luhn_checksum(partial: str) -> int:
    digits = [int(d) for d in partial]
    for i in range(len(digits) - 1, -1, -2):
        digits[i] *= 2
        if digits[i] > 9:
            digits[i] -= 9
    total = sum(digits)
    return (10 - (total % 10)) % 10


def generate_card_number(country: str | None = None) -> tuple[str, str]:
    """Return (pan, brand) with Luhn-valid number from country BIN pool."""
    code = (country or "").strip().upper()
    bins = CARD_BINS.get(code) or _FALLBACK_BINS
    prefix, length, brand = random.choice(bins)
    middle_len = max(0, int(length) - len(prefix) - 1)
    partial = prefix + "".join(str(random.randint(0, 9)) for _ in range(middle_len))
    number = partial + str(_luhn_checksum(partial))
    return number, brand


# ---------------------------------------------------------------------------
# Email domains
# ---------------------------------------------------------------------------

EMAIL_DOMAINS: dict[str, list[str]] = {
    "TH": ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com"],
    "JP": ["gmail.com", "yahoo.co.jp", "outlook.jp", "hotmail.com"],
    "US": ["gmail.com", "outlook.com", "yahoo.com", "icloud.com", "hotmail.com"],
    "BR": ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com.br", "uol.com.br"],
    "GB": ["gmail.com", "outlook.com", "yahoo.co.uk", "hotmail.co.uk", "icloud.com"],
    "KR": ["gmail.com", "naver.com", "daum.net", "outlook.com"],
    "TW": ["gmail.com", "yahoo.com.tw", "hotmail.com", "outlook.com"],
    "HK": ["gmail.com", "yahoo.com.hk", "outlook.com", "hotmail.com"],
    "SG": ["gmail.com", "outlook.com", "yahoo.com.sg", "hotmail.com"],
    "VN": ["gmail.com", "yahoo.com.vn", "outlook.com", "hotmail.com"],
    "CN": ["gmail.com", "outlook.com", "yahoo.com", "163.com", "qq.com"],
    "NL": ["gmail.com", "outlook.com", "hotmail.nl", "live.nl"],
    "MX": ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com.mx"],
    "ID": ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"],
    "MY": ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"],
    "PH": ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"],
    "AU": ["gmail.com", "outlook.com", "yahoo.com.au", "hotmail.com"],
    "CA": ["gmail.com", "outlook.com", "yahoo.ca", "hotmail.com", "icloud.com"],
    "DE": ["gmail.com", "outlook.com", "web.de", "gmx.de", "hotmail.de"],
    "FR": ["gmail.com", "outlook.com", "orange.fr", "hotmail.fr", "yahoo.fr"],
    "ES": ["gmail.com", "outlook.com", "hotmail.es", "yahoo.es"],
    "IT": ["gmail.com", "outlook.com", "libero.it", "hotmail.it"],
    "NZ": ["gmail.com", "outlook.com", "yahoo.co.nz", "hotmail.com"],
}

_DEFAULT_EMAIL_DOMAINS = ["gmail.com", "outlook.com", "yahoo.com", "hotmail.com"]


def pick_email_domain(country: str | None = None) -> str:
    code = (country or "").strip().upper()
    return random.choice(EMAIL_DOMAINS.get(code) or _DEFAULT_EMAIL_DOMAINS)


# ---------------------------------------------------------------------------
# Content language / identifier
# ---------------------------------------------------------------------------

CONTENT_LANG: dict[str, str] = {
    "TH": "th", "JP": "ja", "US": "en", "BR": "pt", "GB": "en",
    "KR": "ko", "TW": "zh", "HK": "zh", "SG": "en", "VN": "vi",
    "CN": "zh", "NL": "nl", "MX": "es", "ID": "id", "MY": "ms",
    "PH": "en", "AU": "en", "CA": "en", "DE": "de", "FR": "fr",
    "ES": "es", "IT": "it", "NZ": "en",
}

# Optional observed full hashes from successful dumps (prefer live extract).
KNOWN_CONTENT_HASH: dict[str, str] = {
    "TH": "ad71d3f143dd4ff8804fdf7dc6b3df2b",
}


def content_lang(country: str | None = None) -> str:
    code = (country or "TH").strip().upper()
    return CONTENT_LANG.get(code, "en")


def short_content_identifier(country: str | None = None, lang: str | None = None) -> str:
    code = (country or "TH").strip().upper()
    lg = (lang or content_lang(code)).strip().lower() or "en"
    return f"{code}:{lg}:compliance.signupTerms"


def full_content_identifier(
    country: str | None = None,
    lang: str | None = None,
    content_hash: str | None = None,
) -> str:
    code = (country or "TH").strip().upper()
    lg = (lang or content_lang(code)).strip().lower() or "en"
    h = (content_hash or KNOWN_CONTENT_HASH.get(code) or "").strip().lower()
    if h and re.fullmatch(r"[0-9a-f]{32}", h):
        return f"{code}:{lg}:{h}:compliance.signupTerms"
    return short_content_identifier(code, lg)


def content_manifest_hints(country: str | None = None) -> dict[str, Any]:
    code = (country or "TH").strip().upper()
    lg = content_lang(code)
    known = KNOWN_CONTENT_HASH.get(code, "")
    return {
        "country": code,
        "lang": lg,
        "short_identifier": short_content_identifier(code, lg),
        "known_hash": known or None,
        "full_identifier": full_content_identifier(code, lg) if known else None,
        "prefer_live_extract": True,
        "depth": "gold" if code in {"TH", "JP", "US", "BR", "GB"} else "solid",
    }

# ---------------------------------------------------------------------------
# Address pools (ASCII / form-safe)
# ---------------------------------------------------------------------------

ADDRESS_POOLS: dict[str, list[dict[str, Any]]] = {
    "TH": [
        {"state": "Bangkok", "city": "Bangkok", "district": "Pathum Wan", "postal": "10330",
         "streets": ["Sukhumvit Road", "Ratchadamri Road", "Wireless Road", "Phloen Chit Road"]},
        {"state": "Bangkok", "city": "Bangkok", "district": "Watthana", "postal": "10110",
         "streets": ["Sukhumvit Road", "Asok Montri Road", "Thong Lo Road", "Ekkamai Road"]},
        {"state": "Bangkok", "city": "Bangkok", "district": "Bang Rak", "postal": "10500",
         "streets": ["Silom Road", "Sathorn Road", "Charoen Krung Road", "Surawong Road"]},
        {"state": "Bangkok", "city": "Bangkok", "district": "Chatuchak", "postal": "10900",
         "streets": ["Phahonyothin Road", "Lat Phrao Road", "Vibhavadi Rangsit Road"]},
        {"state": "Bangkok", "city": "Bangkok", "district": "Huai Khwang", "postal": "10310",
         "streets": ["Ratchadaphisek Road", "Phetchaburi Road", "Din Daeng Road"]},
        {"state": "Chiang Mai", "city": "Chiang Mai", "district": "Mueang", "postal": "50200",
         "streets": ["Huay Kaew Road", "Nimmanahaeminda Road", "Chang Klan Road", "Tha Phae Road"]},
        {"state": "Chiang Mai", "city": "Chiang Mai", "district": "Hang Dong", "postal": "50230",
         "streets": ["Chiang Mai-Hang Dong Road", "Ban Waen Road"]},
        {"state": "Phuket", "city": "Phuket", "district": "Mueang", "postal": "83000",
         "streets": ["Phuket Road", "Yaowarat Road", "Thepkrasattri Road"]},
        {"state": "Phuket", "city": "Phuket", "district": "Kathu", "postal": "83120",
         "streets": ["Patak Road", "Na Nai Road", "Vichitsongkram Road"]},
        {"state": "Chon Buri", "city": "Pattaya", "district": "Bang Lamung", "postal": "20150",
         "streets": ["Pattaya Beach Road", "Second Road", "Third Road", "Sukhumvit Road"]},
        {"state": "Chon Buri", "city": "Chon Buri", "district": "Si Racha", "postal": "20110",
         "streets": ["Sukhumvit Road", "Jermjompol Road"]},
        {"state": "Nonthaburi", "city": "Nonthaburi", "district": "Mueang", "postal": "11000",
         "streets": ["Rattanathibet Road", "Ngarmwongwan Road", "Tiwanon Road"]},
        {"state": "Samut Prakan", "city": "Samut Prakan", "district": "Mueang", "postal": "10270",
         "streets": ["Sukhumvit Road", "Pu Chao Saming Phrai Road"]},
        {"state": "Khon Kaen", "city": "Khon Kaen", "district": "Mueang", "postal": "40000",
         "streets": ["Mittraphap Road", "Na Muang Road", "Srichan Road"]},
        {"state": "Nakhon Ratchasima", "city": "Nakhon Ratchasima", "district": "Mueang", "postal": "30000",
         "streets": ["Mittraphap Road", "Chomsurangyat Road"]},
        {"state": "Songkhla", "city": "Hat Yai", "district": "Hat Yai", "postal": "90110",
         "streets": ["Phetkasem Road", "Niphat Uthit Road", "Sriphuwanat Road"]},
        {"state": "Udon Thani", "city": "Udon Thani", "district": "Mueang", "postal": "41000",
         "streets": ["Pho Si Road", "Udon-Dutsadi Road"]},
        {"state": "Surat Thani", "city": "Surat Thani", "district": "Mueang", "postal": "84000",
         "streets": ["Talad Mai Road", "Chonkasem Road"]},
    ],
    "JP": [
        {"state": "Tokyo", "city": "Shibuya", "district": "Shibuya", "postal": "150-0002",
         "streets": ["Meiji Dori", "Dogenzaka", "Center Gai", "Inokashira Dori"]},
        {"state": "Tokyo", "city": "Shinjuku", "district": "Shinjuku", "postal": "160-0022",
         "streets": ["Yasukuni Dori", "Shinjuku Dori", "Okubo Dori"]},
        {"state": "Tokyo", "city": "Minato", "district": "Roppongi", "postal": "106-0032",
         "streets": ["Roppongi Dori", "Gaien-Higashi Dori", "Azabu Dori"]},
        {"state": "Tokyo", "city": "Chiyoda", "district": "Marunouchi", "postal": "100-0005",
         "streets": ["Gyoko Dori", "Hibiya Dori", "Uchibori Dori"]},
        {"state": "Osaka", "city": "Osaka", "district": "Chuo", "postal": "540-0002",
         "streets": ["Mido Suji", "Sakai Suji", "Nagahori Dori"]},
        {"state": "Osaka", "city": "Osaka", "district": "Kita", "postal": "530-0001",
         "streets": ["Umeda Street", "Midosuji", "Sonezaki Dori"]},
        {"state": "Kyoto", "city": "Kyoto", "district": "Nakagyo", "postal": "604-8005",
         "streets": ["Kawaramachi Street", "Shijo Dori", "Karasuma Dori"]},
        {"state": "Kanagawa", "city": "Yokohama", "district": "Naka", "postal": "231-0023",
         "streets": ["Bashamichi", "Honcho Dori", "Nihon-odori"]},
        {"state": "Aichi", "city": "Nagoya", "district": "Naka", "postal": "460-0008",
         "streets": ["Sakae Street", "Otsu Dori", "Nishiki Dori"]},
        {"state": "Fukuoka", "city": "Fukuoka", "district": "Hakata", "postal": "812-0011",
         "streets": ["Taihaku Dori", "Watanabe Dori", "Sumiyoshi Dori"]},
        {"state": "Hokkaido", "city": "Sapporo", "district": "Chuo", "postal": "060-0001",
         "streets": ["Odori", "Minami Ichijo", "Ekimae Dori"]},
    ],
    "US": [
        {"state": "CA", "city": "San Francisco", "district": "Mission", "postal": "94110",
         "streets": ["Mission Street", "Valencia Street", "24th Street", "Guerrero Street"]},
        {"state": "CA", "city": "Los Angeles", "district": "Downtown", "postal": "90012",
         "streets": ["Spring Street", "Main Street", "Broadway", "Figueroa Street"]},
        {"state": "CA", "city": "San Jose", "district": "Downtown", "postal": "95113",
         "streets": ["Santa Clara Street", "First Street", "San Fernando Street"]},
        {"state": "NY", "city": "New York", "district": "Manhattan", "postal": "10001",
         "streets": ["5th Avenue", "Madison Avenue", "Broadway", "W 34th Street"]},
        {"state": "NY", "city": "Brooklyn", "district": "Williamsburg", "postal": "11211",
         "streets": ["Bedford Avenue", "Berry Street", "Grand Street"]},
        {"state": "TX", "city": "Austin", "district": "Downtown", "postal": "78701",
         "streets": ["Congress Avenue", "6th Street", "Lavaca Street"]},
        {"state": "TX", "city": "Houston", "district": "Midtown", "postal": "77002",
         "streets": ["Main Street", "Travis Street", "Louisiana Street"]},
        {"state": "FL", "city": "Miami", "district": "Brickell", "postal": "33131",
         "streets": ["Brickell Avenue", "SE 1st Street", "Coral Way"]},
        {"state": "IL", "city": "Chicago", "district": "Loop", "postal": "60601",
         "streets": ["Michigan Avenue", "State Street", "Wacker Drive"]},
        {"state": "WA", "city": "Seattle", "district": "Capitol Hill", "postal": "98102",
         "streets": ["Broadway", "Pine Street", "Pike Street"]},
        {"state": "MA", "city": "Boston", "district": "Back Bay", "postal": "02116",
         "streets": ["Newbury Street", "Boylston Street", "Commonwealth Avenue"]},
        {"state": "GA", "city": "Atlanta", "district": "Midtown", "postal": "30308",
         "streets": ["Peachtree Street", "10th Street", "Piedmont Avenue"]},
    ],
}

ADDRESS_POOLS.update({
    "BR": [
        {"state": "SP", "city": "Sao Paulo", "district": "Bela Vista", "postal": "01310-100",
         "streets": ["Avenida Paulista", "Rua Augusta", "Rua da Consolacao"]},
        {"state": "SP", "city": "Sao Paulo", "district": "Pinheiros", "postal": "05422-000",
         "streets": ["Rua dos Pinheiros", "Rua Teodoro Sampaio", "Avenida Reboucas"]},
        {"state": "RJ", "city": "Rio de Janeiro", "district": "Copacabana", "postal": "22041-080",
         "streets": ["Avenida Atlantica", "Rua Barata Ribeiro", "Rua Siqueira Campos"]},
        {"state": "RJ", "city": "Rio de Janeiro", "district": "Ipanema", "postal": "22410-003",
         "streets": ["Rua Visconde de Piraja", "Avenida Vieira Souto"]},
        {"state": "MG", "city": "Belo Horizonte", "district": "Savassi", "postal": "30112-000",
         "streets": ["Avenida Getulio Vargas", "Rua Pernambuco", "Rua da Bahia"]},
        {"state": "RS", "city": "Porto Alegre", "district": "Moinhos de Vento", "postal": "90570-020",
         "streets": ["Rua Padre Chagas", "Avenida Goethe", "Rua Dinarte Ribeiro"]},
        {"state": "PR", "city": "Curitiba", "district": "Batel", "postal": "80420-090",
         "streets": ["Avenida Batel", "Rua Comendador Araujo", "Rua Marechal Deodoro"]},
        {"state": "BA", "city": "Salvador", "district": "Barra", "postal": "40140-130",
         "streets": ["Avenida Sete de Setembro", "Rua Chile", "Avenida Oceania"]},
        {"state": "DF", "city": "Brasilia", "district": "Asa Sul", "postal": "70297-400",
         "streets": ["SQS 308 Bloco A", "CLS 109 Bloco B", "SHIS QI 05"]},
        {"state": "PE", "city": "Recife", "district": "Boa Viagem", "postal": "51020-000",
         "streets": ["Avenida Boa Viagem", "Rua Setubal", "Rua Bruno Veloso"]},
    ],
    "GB": [
        {"state": "England", "city": "London", "district": "Westminster", "postal": "SW1A 1AA",
         "streets": ["Baker Street", "Oxford Street", "Regent Street", "King's Road"]},
        {"state": "England", "city": "London", "district": "Camden", "postal": "NW1 8NH",
         "streets": ["Camden High Street", "Chalk Farm Road", "Parkway"]},
        {"state": "England", "city": "Manchester", "district": "City Centre", "postal": "M1 1AE",
         "streets": ["Deansgate", "Market Street", "Portland Street"]},
        {"state": "England", "city": "Birmingham", "district": "City Centre", "postal": "B1 1AA",
         "streets": ["New Street", "Corporation Street", "Broad Street"]},
        {"state": "England", "city": "Bristol", "district": "City Centre", "postal": "BS1 4DJ",
         "streets": ["Park Street", "Queen Square", "Whiteladies Road"]},
        {"state": "Scotland", "city": "Edinburgh", "district": "Old Town", "postal": "EH1 1YZ",
         "streets": ["Royal Mile", "Princes Street", "George Street"]},
        {"state": "Scotland", "city": "Glasgow", "district": "City Centre", "postal": "G1 1XQ",
         "streets": ["Buchanan Street", "Sauchiehall Street", "Argyle Street"]},
        {"state": "Wales", "city": "Cardiff", "district": "City Centre", "postal": "CF10 1EP",
         "streets": ["Queen Street", "St Mary Street", "Cathedral Road"]},
        {"state": "England", "city": "Leeds", "district": "City Centre", "postal": "LS1 1BA",
         "streets": ["Briggate", "The Headrow", "Albion Street"]},
        {"state": "England", "city": "Liverpool", "district": "City Centre", "postal": "L1 8JQ",
         "streets": ["Bold Street", "Lord Street", "Dale Street"]},
    ],
    "KR": [
        {"state": "Seoul", "city": "Seoul", "district": "Gangnam-gu", "postal": "06236",
         "streets": ["Teheran-ro", "Gangnam-daero", "Apgujeong-ro"]},
        {"state": "Seoul", "city": "Seoul", "district": "Jongno-gu", "postal": "03154",
         "streets": ["Jongno", "Sejong-daero", "Samcheong-ro"]},
        {"state": "Seoul", "city": "Seoul", "district": "Mapo-gu", "postal": "04038",
         "streets": ["Hongik-ro", "Yanghwa-ro", "World Cup-ro"]},
        {"state": "Busan", "city": "Busan", "district": "Haeundae-gu", "postal": "48094",
         "streets": ["Haeundaehaebyeon-ro", "Gunam-ro", "Centum-ro"]},
        {"state": "Incheon", "city": "Incheon", "district": "Namdong-gu", "postal": "21556",
         "streets": ["Artcenter-daero", "Guwol-ro"]},
        {"state": "Gyeonggi", "city": "Suwon", "district": "Yeongtong-gu", "postal": "16517",
         "streets": ["Gwanggyojungang-ro", "Worldcup-ro"]},
        {"state": "Daegu", "city": "Daegu", "district": "Jung-gu", "postal": "41911",
         "streets": ["Dongseong-ro", "Jungang-daero"]},
    ],
    "VN": [
        {"state": "Ho Chi Minh", "city": "Ho Chi Minh City", "district": "District 1", "postal": "700000",
         "streets": ["Nguyen Hue", "Le Loi", "Dong Khoi", "Pasteur"]},
        {"state": "Ho Chi Minh", "city": "Ho Chi Minh City", "district": "Binh Thanh", "postal": "700000",
         "streets": ["Xo Viet Nghe Tinh", "Dien Bien Phu", "Nguyen Xi"]},
        {"state": "Hanoi", "city": "Hanoi", "district": "Hoan Kiem", "postal": "100000",
         "streets": ["Hang Bai", "Trang Tien", "Ly Thai To", "Hang Bong"]},
        {"state": "Hanoi", "city": "Hanoi", "district": "Cau Giay", "postal": "100000",
         "streets": ["Xuan Thuy", "Tran Duy Hung", "Nguyen Khang"]},
        {"state": "Da Nang", "city": "Da Nang", "district": "Hai Chau", "postal": "550000",
         "streets": ["Bach Dang", "Tran Phu", "Nguyen Van Linh"]},
    ],
    "CN": [
        {"state": "Shanghai", "city": "Shanghai", "district": "Huangpu", "postal": "200001",
         "streets": ["Nanjing Road", "Huaihai Road", "Fuzhou Road"]},
        {"state": "Shanghai", "city": "Shanghai", "district": "Xuhui", "postal": "200030",
         "streets": ["Zhaojiabang Road", "Hengshan Road", "Caoxi Road"]},
        {"state": "Beijing", "city": "Beijing", "district": "Chaoyang", "postal": "100020",
         "streets": ["Jianguo Road", "Workers Stadium North Road", "Sanlitun Road"]},
        {"state": "Beijing", "city": "Beijing", "district": "Dongcheng", "postal": "100006",
         "streets": ["Wangfujing Street", "Dongdan North Street"]},
        {"state": "Guangdong", "city": "Shenzhen", "district": "Nanshan", "postal": "518052",
         "streets": ["Houhai Avenue", "Science Park Road", "Nanhai Boulevard"]},
        {"state": "Guangdong", "city": "Guangzhou", "district": "Tianhe", "postal": "510620",
         "streets": ["Tianhe Road", "Sports West Road", "Huangpu Avenue"]},
        {"state": "Zhejiang", "city": "Hangzhou", "district": "Xihu", "postal": "310012",
         "streets": ["Wenyi Road", "Shenti Road", "Xixi Road"]},
    ],
    "HK": [
        {"state": "HK", "city": "Hong Kong", "district": "Central", "postal": "999077",
         "streets": ["Queens Road Central", "Des Voeux Road Central", "Ice House Street"]},
        {"state": "HK", "city": "Hong Kong", "district": "Tsim Sha Tsui", "postal": "999077",
         "streets": ["Nathan Road", "Canton Road", "Salisbury Road"]},
        {"state": "HK", "city": "Hong Kong", "district": "Causeway Bay", "postal": "999077",
         "streets": ["Hennessy Road", "Yee Wo Street", "Jaffe Road"]},
        {"state": "HK", "city": "Hong Kong", "district": "Mong Kok", "postal": "999077",
         "streets": ["Argyle Street", "Portland Street", "Soy Street"]},
        {"state": "HK", "city": "Hong Kong", "district": "Wan Chai", "postal": "999077",
         "streets": ["Johnston Road", "Lockhart Road", "Queen's Road East"]},
    ],
})

ADDRESS_POOLS.update({
    "TW": [
        {"state": "Taipei", "city": "Taipei", "district": "Da'an", "postal": "106",
         "streets": ["Zhongxiao East Road", "Xinyi Road", "Roosevelt Road"]},
        {"state": "Taipei", "city": "Taipei", "district": "Zhongshan", "postal": "104",
         "streets": ["Nanjing East Road", "Minquan East Road", "Linsen North Road"]},
        {"state": "New Taipei", "city": "New Taipei", "district": "Banqiao", "postal": "220",
         "streets": ["Wenhua Road", "Xianmin Boulevard"]},
        {"state": "Taichung", "city": "Taichung", "district": "West District", "postal": "403",
         "streets": ["Taiwan Boulevard", "Gongyi Road", "Yingcai Road"]},
        {"state": "Kaohsiung", "city": "Kaohsiung", "district": "Qianjin", "postal": "801",
         "streets": ["Zhongshan Road", "Wufu Road", "Minsheng Road"]},
    ],
    "SG": [
        {"state": "SG", "city": "Singapore", "district": "Orchard", "postal": "238801",
         "streets": ["Orchard Road", "Scotts Road", "Tanglin Road"]},
        {"state": "SG", "city": "Singapore", "district": "Marina Bay", "postal": "018956",
         "streets": ["Raffles Boulevard", "Bayfront Avenue", "Marina Boulevard"]},
        {"state": "SG", "city": "Singapore", "district": "Bugis", "postal": "188021",
         "streets": ["Victoria Street", "North Bridge Road", "Beach Road"]},
        {"state": "SG", "city": "Singapore", "district": "Tanjong Pagar", "postal": "068808",
         "streets": ["Cecil Street", "Robinson Road", "Anson Road"]},
    ],
    "NL": [
        {"state": "NH", "city": "Amsterdam", "district": "Centrum", "postal": "1012 JS",
         "streets": ["Damrak", "Kalverstraat", "Nieuwendijk", "Prinsengracht"]},
        {"state": "NH", "city": "Amsterdam", "district": "Zuid", "postal": "1071 DJ",
         "streets": ["PC Hooftstraat", "Van Baerlestraat", "Beethovenstraat"]},
        {"state": "ZH", "city": "Rotterdam", "district": "Centrum", "postal": "3011 AD",
         "streets": ["Coolsingel", "Lijnbaan", "Witte de Withstraat"]},
        {"state": "ZH", "city": "The Hague", "district": "Centrum", "postal": "2511 CB",
         "streets": ["Spui", "Grote Marktstraat", "Noordeinde"]},
        {"state": "UT", "city": "Utrecht", "district": "Centrum", "postal": "3511 LX",
         "streets": ["Oudegracht", "Vredenburg", "Neude"]},
    ],
    "MX": [
        {"state": "CDMX", "city": "Mexico City", "district": "Cuauhtemoc", "postal": "06600",
         "streets": ["Paseo de la Reforma", "Avenida Insurgentes", "Calle Amberes"]},
        {"state": "CDMX", "city": "Mexico City", "district": "Benito Juarez", "postal": "03100",
         "streets": ["Avenida Universidad", "Calle Eugenia", "Avenida Coyoacan"]},
        {"state": "JAL", "city": "Guadalajara", "district": "Centro", "postal": "44100",
         "streets": ["Avenida Juarez", "Calle Morelos", "Avenida Americas"]},
        {"state": "NL", "city": "Monterrey", "district": "Centro", "postal": "64000",
         "streets": ["Avenida Constitution", "Calle Morelos", "Avenida Fundidora"]},
    ],
    "ID": [
        {"state": "JK", "city": "Jakarta", "district": "Menteng", "postal": "10310",
         "streets": ["Jalan MH Thamrin", "Jalan Sudirman", "Jalan Wahid Hasyim"]},
        {"state": "JK", "city": "Jakarta", "district": "Kebayoran Baru", "postal": "12120",
         "streets": ["Jalan Senopati", "Jalan Panglima Polim", "Jalan Melawai"]},
        {"state": "JB", "city": "Bandung", "district": "Coblong", "postal": "40132",
         "streets": ["Jalan Dago", "Jalan Merdeka", "Jalan RE Martadinata"]},
        {"state": "JI", "city": "Surabaya", "district": "Gubeng", "postal": "60281",
         "streets": ["Jalan Raya Gubeng", "Jalan Pemuda", "Jalan Basuki Rahmat"]},
    ],
    "AU": [
        {"state": "NSW", "city": "Sydney", "district": "CBD", "postal": "2000",
         "streets": ["George Street", "Pitt Street", "Elizabeth Street"]},
        {"state": "VIC", "city": "Melbourne", "district": "CBD", "postal": "3000",
         "streets": ["Collins Street", "Bourke Street", "Swanston Street"]},
        {"state": "QLD", "city": "Brisbane", "district": "CBD", "postal": "4000",
         "streets": ["Queen Street", "Adelaide Street", "Ann Street"]},
        {"state": "WA", "city": "Perth", "district": "CBD", "postal": "6000",
         "streets": ["St Georges Terrace", "Hay Street", "Murray Street"]},
    ],
    "CA": [
        {"state": "ON", "city": "Toronto", "district": "Downtown", "postal": "M5V 2T6",
         "streets": ["King Street West", "Queen Street West", "Bay Street"]},
        {"state": "BC", "city": "Vancouver", "district": "Downtown", "postal": "V6B 1A1",
         "streets": ["Robson Street", "Granville Street", "Georgia Street"]},
        {"state": "QC", "city": "Montreal", "district": "Ville-Marie", "postal": "H2Y 1C6",
         "streets": ["Rue Sainte-Catherine", "Boulevard Saint-Laurent", "Rue Sherbrooke"]},
        {"state": "AB", "city": "Calgary", "district": "Downtown", "postal": "T2P 1J9",
         "streets": ["Stephen Avenue", "1st Street SW", "8th Avenue SW"]},
    ],
    "DE": [
        {"state": "BE", "city": "Berlin", "district": "Mitte", "postal": "10115",
         "streets": ["Friedrichstrasse", "Unter den Linden", "Torstrasse"]},
        {"state": "BY", "city": "Munich", "district": "Altstadt", "postal": "80331",
         "streets": ["Kaufingerstrasse", "Maximilianstrasse", "Sendlinger Strasse"]},
        {"state": "HH", "city": "Hamburg", "district": "Neustadt", "postal": "20354",
         "streets": ["Jungfernstieg", "Moenckebergstrasse", "Reeperbahn"]},
        {"state": "NW", "city": "Cologne", "district": "Innenstadt", "postal": "50667",
         "streets": ["Hohe Strasse", "Schildergasse", "Ehrenstrasse"]},
    ],
    "FR": [
        {"state": "IDF", "city": "Paris", "district": "1er", "postal": "75001",
         "streets": ["Rue de Rivoli", "Avenue de l Opera", "Rue Saint-Honore"]},
        {"state": "IDF", "city": "Paris", "district": "11e", "postal": "75011",
         "streets": ["Boulevard Voltaire", "Rue Oberkampf", "Avenue de la Republique"]},
        {"state": "ARA", "city": "Lyon", "district": "2e", "postal": "69002",
         "streets": ["Rue de la Republique", "Quai Saint-Antoine"]},
        {"state": "PACA", "city": "Marseille", "district": "1er", "postal": "13001",
         "streets": ["La Canebiere", "Rue Saint-Ferreol"]},
    ],
})


def _house_number(country: str) -> str:
    code = (country or "").strip().upper()
    if code == "JP":
        return f"{random.randint(1, 28)}-{random.randint(1, 20)}-{random.randint(1, 15)}"
    if code == "TH":
        base = str(random.randint(12, 999))
        if random.random() < 0.35:
            return f"{base}/{random.randint(1, 20)}"
        return base
    if code == "GB":
        return str(random.randint(1, 220))
    if code in {"US", "CA", "AU", "NZ"}:
        return str(random.randint(10, 8999))
    if code == "BR":
        return str(random.randint(12, 4899))
    if code in {"DE", "KR"}:
        return str(random.randint(1, 180))
    if code == "NL":
        num = str(random.randint(1, 240))
        if random.random() < 0.25:
            return f"{num}{random.choice(list('ABCDEF'))}"
        return num
    return str(random.randint(1, 999))


def generate_address_dict(country: str) -> dict[str, str]:
    """Return a form-safe address dict for the given ISO2 country."""
    code = (country or "TH").strip().upper()
    pool = ADDRESS_POOLS.get(code)
    if not pool:
        return {
            "street": "Main Street",
            "house_number": str(random.randint(1, 999)),
            "district": "Center",
            "city": "Capital",
            "state": code,
            "postal_code": f"{random.randint(10000, 99999)}",
            "country": code,
        }
    loc = random.choice(pool)
    streets = loc.get("streets") or ["Main Street"]
    street = random.choice(list(streets))
    return {
        "street": str(street)[:80],
        "house_number": _house_number(code)[:12],
        "district": str(loc.get("district") or loc.get("city") or "Center")[:60],
        "city": str(loc.get("city") or "Capital")[:60],
        "state": str(loc.get("state") or code)[:30],
        "postal_code": str(loc.get("postal") or "")[:16],
        "country": code,
    }


def profile_depth(country: str | None = None) -> dict[str, Any]:
    code = (country or "TH").strip().upper()
    gold = code in {"TH", "JP", "US", "BR", "GB"}
    solid = code in ADDRESS_POOLS and code in CARD_BINS and code in PHONE_RULES
    return {
        "country": code,
        "tier": "gold" if gold else ("solid" if solid else "template"),
        "phone_rules": code in PHONE_RULES,
        "address_pool_size": len(ADDRESS_POOLS.get(code) or []),
        "card_bins": len(CARD_BINS.get(code) or []),
        "email_domains": len(EMAIL_DOMAINS.get(code) or []),
        "content": content_manifest_hints(code),
    }
