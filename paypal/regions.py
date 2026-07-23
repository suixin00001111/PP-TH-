"""Per-country protocol profiles for multi-country BA flow.

Brazil (openai-paypal) is the deep risk/session reference implementation.
Each market reuses that runtime depth but binds its own protocol knobs:
locale, language, dial code, analytics offset, identity rules, address shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RegionProfile:
    code: str
    name_zh: str
    name_en: str
    lang: str
    locale_bcp47: str
    locale_tag: str
    phone_cc: str
    phone_cc_digits: str
    analytics_offset_min: int
    phone_placeholder: str
    sample_local: str
    phone_hint: str = ""
    protocol_base: str = "BR"  # deep risk/session base (Brazil-depth)
    require_identity: bool = False
    identity_type: str | None = None
    send_identity_document: bool = False

    def accept_language_header(self) -> str:
        return f"{self.locale_bcp47},{self.lang};q=0.9,en-US;q=0.8,en;q=0.7"

    def protocol_summary(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name_zh": self.name_zh,
            "protocol_base": self.protocol_base,
            "lang": self.lang,
            "locale": self.locale_bcp47,
            "locale_tag": self.locale_tag,
            "phone_cc": self.phone_cc,
            "analytics_g": self.analytics_offset_min,
            "identity": self.identity_type if self.send_identity_document else None,
        }


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
    *,
    require_identity: bool = False,
    identity_type: str | None = None,
    send_identity_document: bool = False,
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
        phone_hint=f"+{cc} sample local number",
        protocol_base="BR",
        require_identity=require_identity,
        identity_type=identity_type,
        send_identity_document=send_identity_document,
    )


# name_zh stored as unicode escapes so Windows editors cannot corrupt them
REGIONS: dict[str, RegionProfile] = {
    "TH": _row("TH", "\u6cf0\u56fd", "Thailand", "th", "th-TH", "th_TH", "66", -420, "812345678"),
    "JP": _row("JP", "\u65e5\u672c", "Japan", "ja", "ja-JP", "ja_JP", "81", -540, "9012345678"),
    "US": _row("US", "\u7f8e\u56fd", "United States", "en", "en-US", "en_US", "1", 300, "4155552671"),
    "GB": _row("GB", "\u82f1\u56fd", "United Kingdom", "en", "en-GB", "en_GB", "44", 0, "7400123456"),
    "BR": _row(
        "BR", "\u5df4\u897f", "Brazil", "pt", "pt-BR", "pt_BR", "55", 180, "11987654321",
        require_identity=True, identity_type="CPF", send_identity_document=True,
    ),
    "MX": _row("MX", "\u58a8\u897f\u54e5", "Mexico", "es", "es-MX", "es_MX", "52", 360, "5512345678"),
    "ID": _row("ID", "\u5370\u5ea6\u5c3c\u897f\u4e9a", "Indonesia", "id", "id-ID", "id_ID", "62", -420, "81234567890"),
    "MY": _row("MY", "\u9a6c\u6765\u897f\u4e9a", "Malaysia", "ms", "ms-MY", "ms_MY", "60", -480, "123456789"),
    "SG": _row("SG", "\u65b0\u52a0\u5761", "Singapore", "en", "en-SG", "en_SG", "65", -480, "91234567"),
    "PH": _row("PH", "\u83f2\u5f8b\u5bbe", "Philippines", "en", "en-PH", "en_PH", "63", -480, "9171234567"),
    "VN": _row("VN", "\u8d8a\u5357", "Vietnam", "vi", "vi-VN", "vi_VN", "84", -420, "912345678"),
    "KR": _row("KR", "\u97e9\u56fd", "South Korea", "ko", "ko-KR", "ko_KR", "82", -540, "1012345678"),
    "HK": _row("HK", "\u9999\u6e2f", "Hong Kong", "zh", "zh-HK", "zh_HK", "852", -480, "51234567"),
    "TW": _row("TW", "\u53f0\u6e7e", "Taiwan", "zh", "zh-TW", "zh_TW", "886", -480, "912345678"),
    "CN": _row("CN", "\u4e2d\u56fd", "China", "zh", "zh-CN", "zh_CN", "86", -480, "13800138000"),
    "AU": _row("AU", "\u6fb3\u5927\u5229\u4e9a", "Australia", "en", "en-AU", "en_AU", "61", -600, "412345678"),
    "NZ": _row("NZ", "\u65b0\u897f\u5170", "New Zealand", "en", "en-NZ", "en_NZ", "64", -720, "211234567"),
    "CA": _row("CA", "\u52a0\u62ff\u5927", "Canada", "en", "en-CA", "en_CA", "1", 300, "4165550123"),
    "DE": _row("DE", "\u5fb7\u56fd", "Germany", "de", "de-DE", "de_DE", "49", -60, "15123456789"),
    "FR": _row("FR", "\u6cd5\u56fd", "France", "fr", "fr-FR", "fr_FR", "33", -60, "612345678"),
    "ES": _row("ES", "\u897f\u73ed\u7259", "Spain", "es", "es-ES", "es_ES", "34", -60, "612345678"),
    "IT": _row("IT", "\u610f\u5927\u5229", "Italy", "it", "it-IT", "it_IT", "39", -60, "3123456789"),
    "NL": _row("NL", "\u8377\u5170", "Netherlands", "nl", "nl-NL", "nl_NL", "31", -60, "612345678"),
    "SE": _row("SE", "\u745e\u5178", "Sweden", "sv", "sv-SE", "sv_SE", "46", -60, "701234567"),
    "PL": _row("PL", "\u6ce2\u5170", "Poland", "pl", "pl-PL", "pl_PL", "48", -60, "512345678"),
    "PT": _row("PT", "\u8461\u8404\u7259", "Portugal", "pt", "pt-PT", "pt_PT", "351", 0, "912345678"),
    "IE": _row("IE", "\u7231\u5c14\u5170", "Ireland", "en", "en-IE", "en_IE", "353", 0, "851234567"),
    "CH": _row("CH", "\u745e\u58eb", "Switzerland", "de", "de-CH", "de_CH", "41", -60, "791234567"),
    "AT": _row("AT", "\u5965\u5730\u5229", "Austria", "de", "de-AT", "de_AT", "43", -60, "6641234567"),
    "BE": _row("BE", "\u6bd4\u5229\u65f6", "Belgium", "nl", "nl-BE", "nl_BE", "32", -60, "470123456"),
    "DK": _row("DK", "\u4e39\u9ea6", "Denmark", "da", "da-DK", "da_DK", "45", -60, "20123456"),
    "NO": _row("NO", "\u632a\u5a01", "Norway", "nb", "nb-NO", "nb_NO", "47", -60, "40612345"),
    "FI": _row("FI", "\u82ac\u5170", "Finland", "fi", "fi-FI", "fi_FI", "358", -120, "401234567"),
    "IN": _row("IN", "\u5370\u5ea6", "India", "en", "en-IN", "en_IN", "91", -330, "9876543210"),
    "AE": _row("AE", "\u963f\u8054\u914b", "United Arab Emirates", "ar", "ar-AE", "ar_AE", "971", -240, "501234567"),
    "SA": _row("SA", "\u6c99\u7279\u963f\u62c9\u4f2f", "Saudi Arabia", "ar", "ar-SA", "ar_SA", "966", -180, "501234567"),
    "IL": _row("IL", "\u4ee5\u8272\u5217", "Israel", "he", "he-IL", "he_IL", "972", -120, "501234567"),
    "TR": _row("TR", "\u571f\u8033\u5176", "Turkey", "tr", "tr-TR", "tr_TR", "90", -180, "5321234567"),
    "RU": _row("RU", "\u4fc4\u7f57\u65af", "Russia", "ru", "ru-RU", "ru_RU", "7", -180, "9123456789"),
    "ZA": _row("ZA", "\u5357\u975e", "South Africa", "en", "en-ZA", "en_ZA", "27", -120, "821234567"),
    "AR": _row("AR", "\u963f\u6839\u5ef7", "Argentina", "es", "es-AR", "es_AR", "54", 180, "91123456789"),
    "CL": _row("CL", "\u667a\u5229", "Chile", "es", "es-CL", "es_CL", "56", 240, "912345678"),
    "CO": _row("CO", "\u54e5\u4f26\u6bd4\u4e9a", "Colombia", "es", "es-CO", "es_CO", "57", 300, "3001234567"),
    "PE": _row("PE", "\u79d8\u9c81", "Peru", "es", "es-PE", "es_PE", "51", 300, "912345678"),
}

SUPPORTED_REGIONS = tuple(REGIONS.keys())
DEFAULT_REGION = "TH"


def normalize_region(code: str | None = None) -> str:
    value = (code or DEFAULT_REGION).strip().upper()
    if value == "UK":
        value = "GB"
    if value not in REGIONS:
        raise ValueError(f"unsupported region: {value}")
    return value


def get_region(code: str | None = None) -> RegionProfile:
    return REGIONS[normalize_region(code)]


def normalize_phone(country: str, value: str) -> tuple[str, str, str]:
    """Return (e164, local, phone_cc).

    Empty phone uses the region sample_local so profile generation can run
    without an external SMS number (caller may replace via SMSBower later).
    """
    region = get_region(country)
    raw = (value or "").strip()
    cc = region.phone_cc_digits
    if not raw:
        local = region.sample_local
        return f"+{cc}{local}", local, f"+{cc}"
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        local = region.sample_local
        return f"+{cc}{local}", local, f"+{cc}"
    if raw.lstrip().startswith("+") and not digits.startswith(cc):
        # allow full e164 of another formatting if still same cc via leading +
        # but reject clear wrong-country numbers
        raise ValueError(f"phone must use country code +{cc} for {region.code}")
    if digits.startswith(cc):
        local = digits[len(cc):]
    elif digits.startswith("0") and not digits.startswith(cc):
        local = digits[1:]
    else:
        local = digits
    if not local or not local.isdigit() or not (6 <= len(local) <= 15):
        raise ValueError(f"invalid local phone length for {region.phone_cc}")
    return f"+{cc}{local}", local, f"+{cc}"


def list_regions_public() -> list[dict]:
    from paypal.region_matrix import annotate_region_public

    out = []
    for code in SUPPORTED_REGIONS:
        r = REGIONS[code]
        item = {
            "code": r.code,
            "name_zh": r.name_zh,
            "name_en": r.name_en,
            "locale": r.locale_bcp47,
            "phone_cc": r.phone_cc,
            "phone_placeholder": r.phone_placeholder,
            "identity": r.identity_type if r.send_identity_document else None,
        }
        out.append(annotate_region_public(item))
    return out
