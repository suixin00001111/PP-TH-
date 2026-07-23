"""Country protocol context derived from Brazil-depth runtime + multi-market knobs.

Brazil (`openai-paypal`) is the deep risk / session / fingerprint reference.
Every market reuses that A-layer machine but MUST bind its own protocol context:
locale, language, dial code, analytics offset, identity rules, address shape,
and signup content-identifier language — not a literal copy of BR constants.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paypal.regions import RegionProfile, get_region, normalize_region


@dataclass(frozen=True)
class ProtocolContext:
    """Resolved protocol knobs for one run."""

    code: str
    name_zh: str
    lang: str
    locale_bcp47: str
    locale_tag: str
    phone_cc: str
    phone_cc_digits: str
    analytics_offset_min: int
    phone_placeholder: str
    send_identity_document: bool
    identity_type: str | None
    # Address shaping
    address_style: str  # th | jp | us | eu | br | latam | generic
    # GraphQL / page
    content_lang: str   # language segment inside contentIdentifier
    country_x: str      # country.x query param
    locale_x: str       # locale.x query param
    # Brazil-depth runtime markers (shared machine, country-bound knobs)
    protocol_base: str = "BR"
    accept_language: str = ""

    def __post_init__(self) -> None:
        if not self.accept_language:
            object.__setattr__(
                self,
                "accept_language",
                f"{self.locale_bcp47},{self.lang};q=0.9,en-US;q=0.8,en;q=0.7",
            )

    def summary(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name_zh": self.name_zh,
            "reference": self.protocol_base,
            "lang": self.lang,
            "locale_tag": self.locale_tag,
            "locale_bcp47": self.locale_bcp47,
            "phone_cc": self.phone_cc,
            "analytics_g": self.analytics_offset_min,
            "identity": self.identity_type if self.send_identity_document else None,
            "address_style": self.address_style,
            "content_lang": self.content_lang,
            "accept_language": self.accept_language,
        }


# Address line shaping aligned with regional postal conventions
_ADDRESS_STYLE = {
    "TH": "th",
    "JP": "jp",
    "US": "us",
    "CA": "us",
    "GB": "uk",
    "AU": "us",
    "NZ": "us",
    "BR": "br",
    "MX": "latam",
    "AR": "latam",
    "CL": "latam",
    "CO": "latam",
    "PE": "latam",
    "DE": "eu",
    "FR": "eu",
    "ES": "eu",
    "IT": "eu",
    "NL": "eu",
    "SE": "eu",
    "PL": "eu",
    "PT": "eu",
    "IE": "eu",
    "CH": "eu",
    "AT": "eu",
    "BE": "eu",
    "DK": "eu",
    "NO": "eu",
    "FI": "eu",
    "SG": "us",
    "HK": "us",
    "TW": "us",
    "KR": "us",
    "PH": "us",
    "MY": "us",
    "ID": "us",
    "VN": "us",
    "IN": "us",
    "AE": "us",
    "SA": "us",
    "IL": "us",
    "TR": "eu",
    "RU": "eu",
    "ZA": "us",
    "CN": "us",
}


def build_protocol(country: str | None) -> ProtocolContext:
    """Build country-specific protocol context on the Brazil-depth machine."""
    region: RegionProfile = get_region(country)
    code = region.code
    style = _ADDRESS_STYLE.get(code, "generic")
    accept = region.accept_language_header()
    return ProtocolContext(
        code=code,
        name_zh=region.name_zh,
        lang=region.lang,
        locale_bcp47=region.locale_bcp47,
        locale_tag=region.locale_tag,
        phone_cc=region.phone_cc,
        phone_cc_digits=region.phone_cc_digits,
        analytics_offset_min=region.analytics_offset_min,
        phone_placeholder=region.phone_placeholder,
        send_identity_document=bool(region.send_identity_document),
        identity_type=region.identity_type,
        address_style=style,
        content_lang=region.lang,
        country_x=code,
        locale_x=region.locale_tag,
        protocol_base=getattr(region, "protocol_base", "BR") or "BR",
        accept_language=accept,
    )


def format_billing_line1(style: str, street: str, house_number: str, district: str = "") -> str:
    """Country-shaped address line1."""
    street = (street or "").strip()
    house = (house_number or "").strip()
    district = (district or "").strip()
    if style == "jp":
        return f"{street} {house}".strip()
    if style == "us" or style == "uk":
        return f"{house} {street}".strip()
    if style == "eu":
        return f"{street} {house}".strip()
    if style in {"br", "latam", "th"}:
        return f"{street}, {house}".strip()
    return f"{street}, {house}".strip()


def format_billing_line2(style: str, district: str) -> str:
    district = (district or "").strip()
    if style in {"us", "uk"}:
        return ""
    return district


def should_send_identity(code: str) -> bool:
    """Only Brazil submits CPF identity document (Brazil package behavior)."""
    try:
        return bool(get_region(code).send_identity_document)
    except Exception:
        return str(code or "").upper() == "BR"


def protocol_locale_pair(country: str | None) -> tuple[str, str]:
    """Return (country_code, lang) for 2FA / weasley / Griffin payloads."""
    p = build_protocol(country)
    return p.code, p.lang
