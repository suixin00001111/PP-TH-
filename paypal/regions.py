"""Multi-country protocol profiles for pure-HTTP BA flow.

Protocol mechanics follow the Thailand implementation; each country only
swaps locale / phone dial code / analytics timezone / profile templates.
"""
from __future__ import annotations

from dataclasses import dataclass
import random
import re


@dataclass(frozen=True)
class RegionProfile:
    code: str
    name_zh: str
    name_en: str
    lang: str
    locale_bcp47: str
    locale_tag: str
    phone_cc: str          # +66
    phone_cc_digits: str   # 66
    analytics_offset_min: int
    phone_placeholder: str
    sample_local: str
    phone_hint: str = ""

    def accept_language_header(self) -> str:
        return f"{self.locale_bcp47},{self.lang};q=0.9,en-US;q=0.8,en;q=0.7"


def _row(
    code: str,
    name_zh: str,
    name_en: str,
    lang: str,
    locale_bcp47: str,
    locale_tag: str,
    cc: str,
    offset: int,
    sample_local: str,
) -> RegionProfile:
    return RegionProfile(
        code=code,
        name_zh=name_zh,
        name_en=name_en,
        lang=lang,
        locale_bcp47=locale_bcp47,
        locale_tag=locale_tag,
        phone_cc=f"+{cc}",
        phone_cc_digits=cc,
        analytics_offset_min=offset,
        phone_placeholder=f"+{cc}{sample_local}",
        sample_local=sample_local,
        phone_hint=f"请填写带国际区号的号码，例如 +{cc}…",
    )


REGIONS: dict[str, RegionProfile] = {
    "TH": _row("TH", "泰国", "Thailand", "th", "th-TH", "th_TH", "66", 420, "812345678"),
    "JP": _row("JP", "日本", "Japan", "ja", "ja-JP", "ja_JP", "81", 540, "9012345678"),
    "US": _row("US", "美国", "United States", "en", "en-US", "en_US", "1", -300, "2025550123"),
    "GB": _row("GB", "英国", "United Kingdom", "en", "en-GB", "en_GB", "44", 0, "7400123456"),
    "BR": _row("BR", "巴西", "Brazil", "pt", "pt-BR", "pt_BR", "55", -180, "11987654321"),
    "MX": _row("MX", "墨西哥", "Mexico", "es", "es-MX", "es_MX", "52", -360, "5512345678"),
    "ID": _row("ID", "印尼", "Indonesia", "id", "id-ID", "id_ID", "62", 420, "81234567890"),
    "MY": _row("MY", "马来西亚", "Malaysia", "ms", "ms-MY", "ms_MY", "60", 480, "123456789"),
    "SG": _row("SG", "新加坡", "Singapore", "en", "en-SG", "en_SG", "65", 480, "91234567"),
    "PH": _row("PH", "菲律宾", "Philippines", "en", "en-PH", "en_PH", "63", 480, "9171234567"),
    "VN": _row("VN", "越南", "Vietnam", "vi", "vi-VN", "vi_VN", "84", 420, "912345678"),
    "KR": _row("KR", "韩国", "South Korea", "ko", "ko-KR", "ko_KR", "82", 540, "1012345678"),
    "HK": _row("HK", "中国香港", "Hong Kong", "zh", "zh-HK", "zh_HK", "852", 480, "91234567"),
    "TW": _row("TW", "中国台湾", "Taiwan", "zh", "zh-TW", "zh_TW", "886", 480, "912345678"),
    "CN": _row("CN", "中国大陆", "China", "zh", "zh-CN", "zh_CN", "86", 480, "13812345678"),
    "AU": _row("AU", "澳大利亚", "Australia", "en", "en-AU", "en_AU", "61", 600, "412345678"),
    "NZ": _row("NZ", "新西兰", "New Zealand", "en", "en-NZ", "en_NZ", "64", 720, "211234567"),
    "CA": _row("CA", "加拿大", "Canada", "en", "en-CA", "en_CA", "1", -300, "4165550123"),
    "DE": _row("DE", "德国", "Germany", "de", "de-DE", "de_DE", "49", 60, "15123456789"),
    "FR": _row("FR", "法国", "France", "fr", "fr-FR", "fr_FR", "33", 60, "612345678"),
    "ES": _row("ES", "西班牙", "Spain", "es", "es-ES", "es_ES", "34", 60, "612345678"),
    "IT": _row("IT", "意大利", "Italy", "it", "it-IT", "it_IT", "39", 60, "3123456789"),
    "NL": _row("NL", "荷兰", "Netherlands", "nl", "nl-NL", "nl_NL", "31", 60, "612345678"),
    "SE": _row("SE", "瑞典", "Sweden", "sv", "sv-SE", "sv_SE", "46", 60, "701234567"),
    "PL": _row("PL", "波兰", "Poland", "pl", "pl-PL", "pl_PL", "48", 60, "512345678"),
    "PT": _row("PT", "葡萄牙", "Portugal", "pt", "pt-PT", "pt_PT", "351", 0, "912345678"),
    "IE": _row("IE", "爱尔兰", "Ireland", "en", "en-IE", "en_IE", "353", 0, "851234567"),
    "CH": _row("CH", "瑞士", "Switzerland", "de", "de-CH", "de_CH", "41", 60, "791234567"),
    "AT": _row("AT", "奥地利", "Austria", "de", "de-AT", "de_AT", "43", 60, "6641234567"),
    "BE": _row("BE", "比利时", "Belgium", "fr", "fr-BE", "fr_BE", "32", 60, "470123456"),
    "DK": _row("DK", "丹麦", "Denmark", "da", "da-DK", "da_DK", "45", 60, "20123456"),
    "NO": _row("NO", "挪威", "Norway", "nb", "nb-NO", "nb_NO", "47", 60, "41234567"),
    "FI": _row("FI", "芬兰", "Finland", "fi", "fi-FI", "fi_FI", "358", 120, "401234567"),
    "IN": _row("IN", "印度", "India", "en", "en-IN", "en_IN", "91", 330, "9876543210"),
    "AE": _row("AE", "阿联酋", "United Arab Emirates", "ar", "ar-AE", "ar_AE", "971", 240, "501234567"),
    "SA": _row("SA", "沙特", "Saudi Arabia", "ar", "ar-SA", "ar_SA", "966", 180, "501234567"),
    "IL": _row("IL", "以色列", "Israel", "he", "he-IL", "he_IL", "972", 120, "501234567"),
    "TR": _row("TR", "土耳其", "Turkey", "tr", "tr-TR", "tr_TR", "90", 180, "5321234567"),
    "RU": _row("RU", "俄罗斯", "Russia", "ru", "ru-RU", "ru_RU", "7", 180, "9123456789"),
    "ZA": _row("ZA", "南非", "South Africa", "en", "en-ZA", "en_ZA", "27", 120, "821234567"),
    "AR": _row("AR", "阿根廷", "Argentina", "es", "es-AR", "es_AR", "54", -180, "91123456789"),
    "CL": _row("CL", "智利", "Chile", "es", "es-CL", "es_CL", "56", -240, "912345678"),
    "CO": _row("CO", "哥伦比亚", "Colombia", "es", "es-CO", "es_CO", "57", -300, "3001234567"),
    "PE": _row("PE", "秘鲁", "Peru", "es", "es-PE", "es_PE", "51", -300, "912345678"),
}

DEFAULT_REGION = "TH"
SUPPORTED_REGIONS = tuple(REGIONS.keys())

_ALIASES = {
    "THAILAND": "TH", "JAPAN": "JP", "JPN": "JP", "USA": "US", "UK": "GB",
    "UNITED KINGDOM": "GB", "BRAZIL": "BR", "MEXICO": "MX", "INDONESIA": "ID",
    "CHINA": "CN", "ZH": "CN", "国内": "CN", "中国": "CN", "日本": "JP", "泰国": "TH",
    "KOREA": "KR", "SOUTH KOREA": "KR", "HONG KONG": "HK", "TAIWAN": "TW",
    "SINGAPORE": "SG", "MALAYSIA": "MY", "VIETNAM": "VN", "PHILIPPINES": "PH",
    "AUSTRALIA": "AU", "CANADA": "CA", "GERMANY": "DE", "FRANCE": "FR",
    "SPAIN": "ES", "ITALY": "IT", "INDIA": "IN", "UAE": "AE", "RUSSIA": "RU",
}


def normalize_region(code: str | None) -> str:
    value = (code or DEFAULT_REGION).strip().upper()
    value = _ALIASES.get(value, value)
    if value not in REGIONS:
        raise ValueError(
            f"不支持的国家/地区：{code}（可选：{', '.join(SUPPORTED_REGIONS)}）"
        )
    return value


def get_region(code: str | None = None) -> RegionProfile:
    return REGIONS[normalize_region(code)]


def normalize_phone(country: str, phone: str = "") -> tuple[str, str, str]:
    """Return (e164, local, +cc).

    Only requires that the number uses the selected country's international
    dialing code. Local subscriber number is not strictly validated.
    """
    region = get_region(country)
    cc = region.phone_cc_digits
    raw = (phone or "").strip()
    if raw.lower().startswith("phone:"):
        raw = raw.split(":", 1)[1].strip()

    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        # auto sample for generators
        local = region.sample_local
        return f"+{cc}{local}", local, f"+{cc}"

    # If user explicitly provided another country calling code, reject.
    if raw.lstrip().startswith("+") and not digits.startswith(cc):
        raise ValueError(
            f"当前协议国家区号为 +{cc}，请填写 {region.phone_cc} 开头的号码"
        )

    # Strip country code if present
    if digits.startswith(cc):
        local = digits[len(cc):]
    elif digits.startswith("0") and not digits.startswith(cc):
        # national trunk 0 — drop one leading 0
        local = digits[1:]
    else:
        local = digits

    # If user typed full e164 without +, digits already handled above
    if not local or not local.isdigit():
        raise ValueError(f"手机号本地号码无效，请填写 {region.phone_cc} 开头的号码")

    # Minimum local length (very loose)
    if len(local) < 6 or len(local) > 15:
        raise ValueError(
            f"手机号长度异常，请填写 {region.phone_cc} + 本地号码（6–15 位）"
        )

    # If original digits don't start with country code and look like full intl of another country
    # Accept local-only input and force selected country code.
    e164 = f"+{cc}{local}"
    return e164, local, f"+{cc}"


def list_regions_public() -> list[dict]:
    out = []
    for code in SUPPORTED_REGIONS:
        r = REGIONS[code]
        out.append(
            {
                "code": r.code,
                "name_zh": r.name_zh,
                "name_en": r.name_en,
                "locale": r.locale_bcp47,
                "phone_cc": r.phone_cc,
                "phone_placeholder": r.phone_placeholder,
                "phone_hint": r.phone_hint or f"区号 {r.phone_cc}",
            }
        )
    return out
