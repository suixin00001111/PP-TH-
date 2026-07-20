"""Country protocol context derived from the Thailand reference flow.

Thailand (`TH`) is the reference implementation of the BA HTTP state machine.
Every other market reuses that machine but MUST bind its own protocol context:
locale, language, dial code, analytics offset, identity rules, address shape,
and signup content-identifier language — not a literal copy of TH constants.
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
    address_style: str  # th | jp | us | eu | generic
    # GraphQL / page
    content_lang: str   # language segment inside contentIdentifier
    country_x: str      # country.x query param
    locale_x: str       # locale.x query param

    @property
    def accept_language(self) -> str:
        return f"{self.locale_bcp47},{self.lang};q=0.9,en-US;q=0.8,en;q=0.7"

    def summary(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name_zh": self.name_zh,
            "reference": "TH",
            "lang": self.lang,
            "locale_tag": self.locale_tag,
            "locale_bcp47": self.locale_bcp47,
            "phone_cc": self.phone_cc,
            "analytics_g": self.analytics_offset_min,
            "identity": self.identity_type if self.send_identity_document else None,
            "address_style": self.address_style,
            "content_lang": self.content_lang,
        }


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
}


def build_protocol(country: str | None) -> ProtocolContext:
    """Build country-specific protocol context from the TH reference machine."""
    region: RegionProfile = get_region(country)
    code = region.code
    style = _ADDRESS_STYLE.get(code, "generic")
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
        send_identity_document=region.send_identity_document,
        identity_type=region.identity_type,
        address_style=style,
        content_lang=region.lang,
        country_x=code,
        locale_x=region.locale_tag,
    )


def format_billing_line1(style: str, street: str, house_number: str, district: str = "") -> str:
    """Country-shaped address line1 (TH reference variants)."""
    street = (street or "").strip()
    house = (house_number or "").strip()
    district = (district or "").strip()
    if style == "jp":
        # JP often: street + house (chome-banchi style already in house)
        return f"{street} {house}".strip()
    if style == "us" or style == "uk":
        return f"{house} {street}".strip()
    if style == "eu":
        return f"{street} {house}".strip()
    if style == "br" or style == "latam":
        return f"{street}, {house}".strip()
    if style == "th":
        return f"{street}, {house}".strip()
    return f"{street}, {house}".strip()


def format_billing_line2(style: str, district: str) -> str:
    district = (district or "").strip()
    if style in {"us", "uk"}:
        return ""  # district usually not separate
    return district
