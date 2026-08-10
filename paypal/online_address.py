"""Online country address resolution (OpenStreetMap Nominatim / Overpass).

Used by generate_address(): try online first, fall back to local pools/Faker.
"""
from __future__ import annotations

import json
import os
import random
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from paypal.models import BillingAddress

ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data" / "runtime_address_cache.json"
CACHE_TTL_SECONDS = 90 * 24 * 60 * 60
_LOCK = threading.Lock()
_CACHE_IO_LOCK = threading.Lock()
_COUNTRY_LOCKS: dict[str, threading.Lock] = {}
_LAST_REQUEST_AT = 0.0

_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
)
_NOMINATIM_ENDPOINTS = (
    "https://nominatim.openstreetmap.org/search",
)

_COUNTRY_CITY_HINTS = {
    "AR": "Buenos Aires", "AT": "Vienna", "AU": "Sydney", "BA": "Sarajevo",
    "BE": "Brussels", "BH": "Manama", "BR": "Sao Paulo", "CA": "Toronto",
    "CH": "Zurich", "CL": "Santiago", "CO": "Bogota", "CZ": "Prague",
    "DE": "Berlin", "DK": "Copenhagen", "ES": "Madrid", "FI": "Helsinki",
    "FR": "Paris", "GB": "London", "GR": "Athens", "HK": "Hong Kong",
    "ID": "Jakarta", "IE": "Dublin", "IL": "Tel Aviv", "IN": "Delhi",
    "IT": "Rome", "JP": "Tokyo", "KR": "Seoul", "MX": "Mexico City",
    "MY": "Kuala Lumpur", "NL": "Amsterdam", "NO": "Oslo", "NZ": "Auckland",
    "PE": "Lima", "PH": "Manila", "PL": "Warsaw", "PT": "Lisbon",
    "QA": "Doha", "SA": "Riyadh", "SE": "Stockholm", "SG": "Singapore",
    "TH": "Bangkok", "TR": "Istanbul", "TW": "Taipei", "US": "New York",
    "VN": "Ho Chi Minh City", "ZA": "Johannesburg", "AE": "Dubai", "RO": "Bucharest",
}

_COUNTRY_POSTAL_HINTS = {
    "AR": "C1001", "AT": "1010", "AU": "2000", "BA": "71000", "BE": "1000",
    "BH": "317", "BR": "01001-000", "CA": "M5H 2N2", "CH": "8001",
    "CL": "8320000", "CO": "110111", "CZ": "110 00", "DE": "10115",
    "DK": "1559", "ES": "28001", "FI": "00100", "FR": "75001",
    "GB": "SW1A 1AA", "GR": "105 63", "ID": "10110", "IE": "D02 X285",
    "IL": "6100000", "IN": "110001", "IT": "00184", "JP": "100-0001",
    "KR": "04524", "MX": "06000", "MY": "50000", "NL": "1012 JS",
    "NO": "0154", "NZ": "1010", "PE": "15001", "PH": "1000",
    "PL": "00-001", "PT": "1000-001", "SA": "11564", "SE": "111 29",
    "SG": "018989", "TH": "10200", "TR": "34000", "TW": "100",
    "US": "10001", "VN": "700000", "ZA": "2000", "RO": "010011", "AE": "00000",
}

_US_STATE_CODES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}


def online_address_enabled(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return bool(explicit)
    raw = os.getenv("PAYPAL_ONLINE_ADDRESS", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _country_lock(code: str) -> threading.Lock:
    with _LOCK:
        return _COUNTRY_LOCKS.setdefault(code, threading.Lock())


def _country_name(code: str) -> str:
    return _COUNTRY_CITY_HINTS.get(code, code)


def _normalize_state(country: str, value: str, iso_code: str = "") -> str:
    state = str(value or "").strip()
    if country != "US":
        return state
    iso = str(iso_code or "").strip().upper()
    if iso.startswith("US-") and len(iso) == 5:
        return iso[-2:]
    if len(state) == 2:
        return state.upper()
    return _US_STATE_CODES.get(state.lower(), state)


def _payload(address: BillingAddress) -> dict[str, str]:
    return {
        "line1": f"{address.house_number} {address.street}".strip(),
        "line2": address.district,
        "city": address.city,
        "state": address.state,
        "postalCode": address.postal_code,
        "street": address.street,
        "house_number": address.house_number,
        "district": address.district,
        "postal_code": address.postal_code,
        "country": address.country,
    }


def validate_address_basic(schema: dict[str, Any], address: dict[str, Any]) -> list[str]:
    """Lightweight field checks. Empty schema => only require street/city."""
    errors: list[str] = []
    fields = schema.get("address_fields") if isinstance(schema, dict) else None
    if not fields:
        for key, label in (
            ("street", "street"),
            ("house_number", "house_number"),
            ("city", "city"),
        ):
            if not str(address.get(key) or "").strip():
                errors.append(f"{label}: required")
        return errors
    aliases = {"postcode": "postalCode", "postal_code": "postalCode"}
    for item in fields:
        if not isinstance(item, dict):
            continue
        name = str(item.get("paypal_name") or "")
        key = aliases.get(name, name)
        value = str(address.get(key) or address.get(name) or "").strip()
        if item.get("required") and not value:
            errors.append(f"{name}: required")
            continue
        if not value:
            continue
        max_length = item.get("max_length")
        min_length = item.get("min_length")
        if isinstance(max_length, int) and len(value) > max_length:
            errors.append(f"{name}: max_length={max_length}")
        if isinstance(min_length, int) and len(value) < min_length:
            errors.append(f"{name}: min_length={min_length}")
        pattern = item.get("pattern")
        if pattern:
            try:
                if re.fullmatch(str(pattern), value) is None:
                    errors.append(f"{name}: pattern mismatch")
            except re.error:
                errors.append(f"{name}: invalid pattern")
    return errors


def _load_cache() -> dict[str, Any]:
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save_cache(cache: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CACHE_PATH)


def _from_tags(country: str, tags: dict[str, Any]) -> BillingAddress | None:
    street = str(tags.get("addr:street") or tags.get("addr:place") or "").strip()
    house = str(tags.get("addr:housenumber") or "").strip()
    if not street or not house:
        return None
    city = str(
        tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village")
        or tags.get("addr:municipality") or tags.get("addr:county") or ""
    ).strip()
    state_source = (
        tags.get("addr:county") or tags.get("addr:state") or tags.get("addr:province") or tags.get("addr:region")
        if country == "RO"
        else tags.get("addr:state") or tags.get("addr:province") or tags.get("addr:region")
    )
    state = _normalize_state(
        country,
        str(state_source or "").strip(),
        str(tags.get("ISO3166-2") or tags.get("addr:state_code") or ""),
    )
    district = str(
        tags.get("addr:suburb") or tags.get("addr:district")
        or tags.get("addr:neighbourhood") or tags.get("addr:quarter") or ""
    ).strip()
    postcode = str(tags.get("addr:postcode") or "").strip().upper()
    if country == "JP":
        digits = re.sub(r"[^0-9]", "", unicodedata.normalize("NFKC", postcode))
        postcode = f"{digits[:3]}-{digits[3:]}" if len(digits) == 7 else postcode
    if not city:
        city = _COUNTRY_CITY_HINTS.get(country, country)
    if not state:
        state = city or country
    if not postcode:
        postcode = _COUNTRY_POSTAL_HINTS.get(country, "")
    if not district:
        district = city
    return BillingAddress(street, house, district, city, state, postcode, country)


def _from_nominatim(country: str, item: dict[str, Any]) -> BillingAddress | None:
    tags = item.get("address") or {}
    if not isinstance(tags, dict):
        return None
    street = str(
        tags.get("road") or tags.get("pedestrian") or tags.get("residential")
        or tags.get("footway") or tags.get("path") or ""
    ).strip()
    house = str(tags.get("house_number") or "").strip()
    if not house and street:
        try:
            house = str((int(item.get("place_id") or 1) % 180) + 1)
        except (TypeError, ValueError):
            house = "1"
    if not street or not house:
        return None
    city = str(
        tags.get("city") or tags.get("town") or tags.get("village")
        or tags.get("municipality") or tags.get("county") or ""
    ).strip()
    state_source = (
        tags.get("county") or tags.get("state") or tags.get("state_district") or tags.get("province") or tags.get("region")
        if country == "RO"
        else tags.get("state") or tags.get("state_district") or tags.get("province") or tags.get("region")
    )
    state = _normalize_state(
        country,
        str(state_source or "").strip(),
        str(tags.get("ISO3166-2-lvl4") or tags.get("ISO3166-2-lvl6") or ""),
    )
    district = str(
        tags.get("suburb") or tags.get("city_district") or tags.get("quarter")
        or tags.get("neighbourhood") or ""
    ).strip()
    if not state:
        state = city or country
    postcode = str(tags.get("postcode") or _COUNTRY_POSTAL_HINTS.get(country) or "").strip().upper()
    if country == "JP":
        digits = re.sub(r"[^0-9]", "", unicodedata.normalize("NFKC", postcode))
        postcode = f"{digits[:3]}-{digits[3:]}" if len(digits) == 7 else postcode
    if not city:
        city = _COUNTRY_CITY_HINTS.get(country, country)
    if not district:
        district = city
    return BillingAddress(street, house, district, city, state, postcode, country)


def _query_overpass(country: str) -> list[BillingAddress]:
    global _LAST_REQUEST_AT
    if country == "US":
        query = (
            '[out:json][timeout:5];'
            f'area["ISO3166-1"="{country}"]->.searchArea;'
            'nwr(area.searchArea)'
            '["building"~"^(house|apartments|residential|detached|semidetached_house|terrace)$"]'
            '["addr:housenumber"]["addr:street"];'
            'out tags 120;'
        )
    else:
        query = (
            '[out:json][timeout:5];'
            f'area["ISO3166-1"="{country}"]->.searchArea;'
            'nwr(area.searchArea)["addr:housenumber"]["addr:street"];'
            'out tags 80;'
        )
    errors: list[str] = []
    for endpoint in _ENDPOINTS[:1]:
        try:
            wait = 1.1 - (time.monotonic() - _LAST_REQUEST_AT)
            if wait > 0:
                time.sleep(wait)
            with httpx.Client(
                timeout=httpx.Timeout(6.0, connect=3.0),
                trust_env=False,
                headers={"User-Agent": "pp-th-address-resolver/1.0"},
            ) as client:
                response = client.post(endpoint, data={"data": query})
            _LAST_REQUEST_AT = time.monotonic()
            response.raise_for_status()
            body = response.json()
            rows: list[BillingAddress] = []
            for element in body.get("elements") or []:
                address = _from_tags(country, element.get("tags") or {})
                if address is not None:
                    rows.append(address)
            if rows:
                return rows
        except Exception as exc:
            errors.append(f"{endpoint}: {exc}")
    raise RuntimeError("online address lookup failed: " + " | ".join(errors))


def _query_nominatim(country: str) -> list[BillingAddress]:
    global _LAST_REQUEST_AT
    errors: list[str] = []
    city = _COUNTRY_CITY_HINTS.get(country, "")
    country_name = _country_name(country)
    queries = list(dict.fromkeys(filter(None, (
        f"hotel {city} {country_name}" if city else f"hotel {country_name}",
        f"apartment {city} {country_name}" if city else f"apartment {country_name}",
    ))))
    for endpoint in _NOMINATIM_ENDPOINTS:
        with httpx.Client(
            timeout=httpx.Timeout(5.0, connect=2.5),
            trust_env=False,
            headers={"User-Agent": "pp-th-address-resolver/1.0", "Accept-Language": "en"},
        ) as client:
            for query in queries:
                try:
                    wait = 1.05 - (time.monotonic() - _LAST_REQUEST_AT)
                    if wait > 0:
                        time.sleep(wait)
                    response = client.get(
                        endpoint,
                        params={
                            "format": "jsonv2",
                            "addressdetails": 1,
                            "limit": 20,
                            "countrycodes": country.lower(),
                            "q": query,
                        },
                    )
                    _LAST_REQUEST_AT = time.monotonic()
                    response.raise_for_status()
                    rows = [
                        address
                        for item in (response.json() or [])
                        if isinstance(item, dict)
                        for address in [_from_nominatim(country, item)]
                        if address is not None
                    ]
                    if rows:
                        return rows
                    errors.append(f"{endpoint} {query}: no address-bearing results")
                except Exception as exc:
                    errors.append(f"{endpoint} {query}: {exc}")
    raise RuntimeError("nominatim address lookup failed: " + " | ".join(errors))


def resolve_online_address(
    country: str,
    schema: dict[str, Any] | None = None,
    *,
    force_refresh: bool = False,
) -> BillingAddress:
    code = str(country or "").strip().upper()
    if len(code) != 2:
        raise ValueError("country must be a two-letter code")
    schema = schema if isinstance(schema, dict) else {}
    with _country_lock(code):
        with _CACHE_IO_LOCK:
            cache = _load_cache()
        cached = cache.get(code) if isinstance(cache.get(code), dict) else None
        stale_address = None
        if cached:
            item = cached.get("address") or {}
            try:
                address = BillingAddress(
                    street=str(item.get("street") or ""),
                    house_number=str(item.get("house_number") or ""),
                    district=str(item.get("district") or ""),
                    city=str(item.get("city") or ""),
                    state=str(item.get("state") or ""),
                    postal_code=str(item.get("postal_code") or ""),
                    country=str(item.get("country") or code),
                )
            except Exception:
                address = None
            if address is not None and not validate_address_basic(schema, _payload(address)):
                stale_address = address
                age_ok = time.time() - float(cached.get("saved_at") or 0) < CACHE_TTL_SECONDS
                if not force_refresh or age_ok:
                    return address
        lookup_errors: list[str] = []
        try:
            rows = _query_nominatim(code)
        except Exception as exc:
            lookup_errors.append(str(exc))
            rows = []
        if not rows:
            try:
                rows = _query_overpass(code)
            except Exception as exc:
                lookup_errors.append(str(exc))
                rows = []
        if not rows:
            if stale_address is not None:
                return stale_address
            raise RuntimeError("online address lookup failed: " + " | ".join(lookup_errors))
        random.shuffle(rows)
        best = None
        best_errors = None
        for address in rows:
            errors = validate_address_basic(schema, _payload(address))
            if not errors:
                best = address
                break
            if best is None or len(errors) < len(best_errors or []):
                best, best_errors = address, errors
        if best is None:
            raise RuntimeError(f"online address lookup returned no usable address for {code}")
        final_errors = validate_address_basic(schema, _payload(best))
        if final_errors:
            # Soft: still accept best candidate if only soft schema issues
            logger.debug("online address soft schema issues for {}: {}", code, final_errors)
        with _CACHE_IO_LOCK:
            latest_cache = _load_cache()
            latest_cache[code] = {
                "saved_at": time.time(),
                "address": {
                    "street": best.street,
                    "house_number": best.house_number,
                    "district": best.district,
                    "city": best.city,
                    "state": best.state,
                    "postal_code": best.postal_code,
                    "country": best.country,
                },
            }
            _save_cache(latest_cache)
        return best


def try_resolve_online_address(
    country: str,
    *,
    enabled: bool | None = None,
    force_refresh: bool = False,
    schema: dict[str, Any] | None = None,
) -> BillingAddress | None:
    """Best-effort online resolve; returns None on disable/failure."""
    if not online_address_enabled(enabled):
        return None
    try:
        address = resolve_online_address(country, schema or {}, force_refresh=force_refresh)
        logger.info(
            "Online address resolved for {}: {}, {} {}",
            str(country).upper(),
            address.street,
            address.city,
            address.postal_code,
        )
        return address
    except Exception as exc:
        logger.warning("Online address unavailable for {}: {}", str(country).upper(), exc)
        return None
