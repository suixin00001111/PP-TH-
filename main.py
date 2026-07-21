#!/usr/bin/env python3
"""PayPal Billing Agreement approval automation.

Usage:
    python main.py --ba-token BA-xxx --phone +66812345678
"""
import argparse
import json
import sys
from pathlib import Path
from loguru import logger

from paypal.oaipy_data import generate_user, generate_card, generate_address
from paypal.regions import normalize_region, list_regions_public
from paypal.flow import PayPalFlow
from paypal.proxy import build_proxy_config
from paypal.session import sanitize_for_log
from paypal.merchant_complete import complete_merchant_chain
from paypal.b_layer_handoff import persist_b_layer_evidence


def main():
    parser = argparse.ArgumentParser(
        description="PayPal Billing Agreement Approval Automation"
    )
    parser.add_argument(
        "--ba-token", required=True,
        help="Billing Agreement token (e.g. BA-xxxxxxxxxxxxxxxxx)"
    )
    parser.add_argument(
        "--phone", required=True,
        help="Phone number with country code (e.g. +66812345678 or +819012345678)"
    )
    parser.add_argument(
        "--country", default="TH",
        help="Protocol country code (TH/JP/US/BR/...)",
    )
    parser.add_argument(
        "--runtime", default=None,
        choices=["protocol", "headless", "auto", "roxy"],
        help="Risk runtime: protocol | headless | auto | roxy",
    )
    parser.add_argument(
        "--smsbower", action="store_true",
        help="Enable SMSBower auto OTP (coexists with manual OTP on Web)",
    )
    parser.add_argument(
        "--smsbower-api-key", default=None,
        help="SMSBower API key (or env SMSBOWER_API_KEY)",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--max-card-attempts",
        type=int,
        default=5,
        help="Max SignUpNewMember retries with fresh generated Visa/MasterCard when addCard fails",
    )
    proxy_group = parser.add_mutually_exclusive_group()
    proxy_group.add_argument(
        "--proxy",
        dest="proxy_enabled",
        action="store_true",
        default=None,
        help="Enable configured 1024proxy outbound proxy for this run",
    )
    proxy_group.add_argument(
        "--no-proxy",
        dest="proxy_enabled",
        action="store_false",
        help="Disable outbound proxy for this run",
    )
    parser.add_argument(
        "--proxy-index",
        type=int,
        default=None,
        help="Use a specific configured proxy index (0-based). Default: random when proxy is enabled",
    )

    args = parser.parse_args()

    logger.remove()
    if args.debug:
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.add(sys.stderr, level="INFO")

    proxy_config = build_proxy_config(enabled=args.proxy_enabled, index=args.proxy_index)
    country = normalize_region(args.country)

    user = generate_user(args.phone, country=country)
    card = generate_card()
    address = generate_address(country=country)

    logger.info(f"User: {user.first_name} {user.last_name}")
    logger.info("Email: {}", sanitize_for_log({"email": user.email})["email"])
    logger.info("Phone: {}", sanitize_for_log({"phone": user.phone})["phone"])
    logger.info("ID: <redacted>")
    logger.info("DOB: <redacted>")
    logger.info(
        "Card: {} exp={} cvv=<redacted>",
        sanitize_for_log({"cardNumber": card.number})["cardNumber"],
        card.expiry,
    )
    logger.info("Address generated: {}, {}-{}", address.district, address.city, address.state)
    logger.info(f"Proxy: {proxy_config.label}")
    logger.info(f"Country/Protocol: {country}")

    flow = PayPalFlow(
        ba_token=args.ba_token,
        user=user,
        card=card,
        address=address,
        max_card_attempts=args.max_card_attempts,
        proxy_config=proxy_config,
        runtime_mode=args.runtime,
        smsbower_enabled=bool(args.smsbower) or None,
        smsbower_api_key=args.smsbower_api_key,
    )

    result = flow.run()
    if isinstance(result, dict) and result.get("status") == "success":
        runtime_dir = Path(__file__).resolve().parent / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        persist_b_layer_evidence(runtime_dir, result)
        merchant = complete_merchant_chain(
            result,
            proxies=[proxy_config.url] if proxy_config.url else None,
            log=lambda message: logger.info(message),
            session_path=str(runtime_dir / "merchant_session.json"),
        )
        result["merchant_chain"] = merchant
        result["merchant_chain_status"] = merchant.get("merchant_chain_status", "")
        result["settlement_status"] = merchant.get("settlement_status", "")

    print("\n" + "=" * 60)
    print("RESULT:")
    print(json.dumps(sanitize_for_log(result), indent=2, ensure_ascii=False))
    print("=" * 60)

    if result.get("status") == "success":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
