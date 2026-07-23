#!/usr/bin/env python3
"""PayPal Billing Agreement automation — multi-country, Brazil-depth protocol."""
import argparse
import json
import sys
from pathlib import Path
from loguru import logger

from paypal.oaipy_data import generate_user, generate_card, generate_address
from paypal.regions import normalize_region
from paypal.flow import PayPalFlow
from paypal.proxy import build_proxy_config
from paypal.session import sanitize_for_log
from paypal.layer_status import annotate_layer_status
from paypal.runtime_config import resolve_and_apply
from paypal.runtime_bridge import build_otp_provider


def main():
    parser = argparse.ArgumentParser(description="PayPal BA multi-country (Brazil-depth protocol)")
    parser.add_argument("--ba-token", required=True)
    parser.add_argument("--phone", required=True)
    parser.add_argument("--country", default="TH")
    parser.add_argument("--profile", default="real", choices=["test", "real"])
    parser.add_argument("--runtime", default=None, choices=["protocol", "headless", "auto", "roxy"])
    parser.add_argument("--fingerprint-source", default=None)
    parser.add_argument("--datadome-mode", default=None)
    parser.add_argument("--mtr-runtime", default=None)
    parser.add_argument("--risk-signals-mode", default=None)
    parser.add_argument("--smsbower", action="store_true")
    parser.add_argument("--smsbower-api-key", default=None)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--max-card-attempts", type=int, default=5)
    parser.add_argument("--max-flow-attempts", type=int, default=1)
    proxy_group = parser.add_mutually_exclusive_group()
    proxy_group.add_argument("--proxy", dest="proxy_enabled", action="store_true", default=None)
    proxy_group.add_argument("--no-proxy", dest="proxy_enabled", action="store_false")
    parser.add_argument("--proxy-index", type=int, default=None)
    parser.add_argument("--proxy-url", default=None)

    args = parser.parse_args()
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if args.debug else "INFO")

    resolved = resolve_and_apply(
        runtime_mode=args.runtime,
        profile=args.profile,
        fingerprint_source=args.fingerprint_source,
        datadome_mode=args.datadome_mode,
        mtr_runtime=args.mtr_runtime,
        risk_signals_mode=args.risk_signals_mode,
        continue_merchant=False,
    )

    proxy_config = build_proxy_config(
        enabled=args.proxy_enabled,
        index=args.proxy_index,
        proxy_url=args.proxy_url,
    )
    country = normalize_region(args.country)
    user = generate_user(args.phone, country=country)
    card = generate_card()
    address = generate_address(country=country)

    logger.info("Country: {}", country)
    logger.info("User: {} {}", user.first_name, user.last_name)
    logger.info("Proxy: {}", proxy_config.label)
    logger.info("Runtime: {}", resolved.as_public_dict())

    sms_provider = None
    if args.smsbower or args.smsbower_api_key:
        sms_provider = build_otp_provider(
            enabled=True,
            api_key=args.smsbower_api_key,
            country_iso=country,
        )

    flow = PayPalFlow(
        ba_token=args.ba_token,
        user=user,
        card=card,
        address=address,
        max_card_attempts=args.max_card_attempts,
        max_flow_attempts=args.max_flow_attempts,
        proxy_config=proxy_config,
        fingerprint_source=resolved.fingerprint_source,
        datadome_mode=resolved.datadome_mode,
        mtr_runtime=resolved.mtr_runtime,
        risk_signals_mode=resolved.risk_signals_mode,
        runtime_mode=resolved.runtime_mode,
        profile=resolved.profile,
        sms_provider=sms_provider,
        smsbower_enabled=bool(args.smsbower) or None,
        smsbower_api_key=args.smsbower_api_key,
        continue_merchant=False,
    )

    try:
        result = flow.run()
    finally:
        try:
            flow.close()
        except Exception:
            pass

    if not isinstance(result, dict):
        result = {"status": "failed", "error": "non-dict result"}
    result["runtime"] = resolved.as_public_dict()
    result.setdefault("region", country)
    annotate_layer_status(result, continue_merchant=False)

    print("\n" + "=" * 60)
    print("RESULT:")
    print(json.dumps(sanitize_for_log(result), indent=2, ensure_ascii=False))
    print("=" * 60)
    sys.exit(0 if str(result.get("status") or "").lower() in {"success", "ok", "completed", "authorized"} else 1)


if __name__ == "__main__":
    main()
