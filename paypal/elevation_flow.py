"""Pure-protocol guest-to-member identity-elevation mode for PP-TH.

Selectable via buyer_identity_mode=identity_elevation / elevate_bind.
Adds a strict EC-token gate plus post-signup BuyerFundingContext hydration
before authorize. Does not launch Chromium.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
import urllib.parse

from loguru import logger

from paypal.flow import PayPalFlow
from paypal.graphql import (
    BUYER_CONTEXT_QUERY,
    BUYER_FUNDING_CONTEXT_QUERY,
    CHECKOUT_SESSION_DATA_QUERY,
)
from paypal.session import sanitize_for_log


class IdentityElevationPayPalFlow(PayPalFlow):
    """PayPal protocol flow with an explicit guest-to-member hydration step."""

    _strict_buyer_context = True

    def _load_review_context(self, url: str, referer: str, max_redirects: int = 8):
        # Once AE BuyerContext has been hydrated, reloading Signup/Hermes can
        # downgrade the same checkout back to ANONYMOUS.
        if (
            str(getattr(self.address, "country", "") or "").upper() in {"AE", "BA"}
            and getattr(self, "_ae_pre_hydrated", False)
        ):
            logger.info(
                "AE/BA pre-hydrated member session preserved; skipping destructive review navigation"
            )
            return SimpleNamespace(
                status_code=204,
                content=b"",
                text="",
                headers={},
                url=url,
            )

        saved_euat = str(getattr(self.state, "euat_token", "") or "")
        # PP-TH uses Hagrid/Hermes helper instead of protocol-package _load_review_context.
        loader = getattr(super(), "_load_review_context", None)
        if callable(loader):
            response = loader(url, referer, max_redirects)
        else:
            hermes_base = self._hermes_url()
            hermes_contingency = self._hermes_url(add_fi_contingency=True)
            review_referer = self._hermes_url(billing_lite=True)
            ok = self._load_hagrid_review_context(hermes_base, hermes_contingency, review_referer)
            response = SimpleNamespace(
                status_code=200 if ok else 500,
                content=b"",
                text="",
                headers={},
                url=url or review_referer,
            )
        if (
            str(getattr(self.address, "country", "") or "").upper() in {"AE", "BA"}
            and saved_euat
            and not self.state.euat_token
        ):
            logger.info("AE/BA review navigation cleared EUAT; restoring signup access token")
            self.session.set_euat_token(saved_euat)
        return response

    @staticmethod
    def _require_checkout_session(result) -> dict:
        item = result[0] if isinstance(result, list) and result else result
        if not isinstance(item, dict):
            raise RuntimeError("IDENTITY_ELEVATION_CONTEXT_INVALID: checkout response type")
        if item.get("errors"):
            detail = ", ".join(
                str(error.get("message") or error.get("name") or "unknown error")
                for error in item.get("errors") or []
                if isinstance(error, dict)
            )
            raise RuntimeError(
                "IDENTITY_ELEVATION_CONTEXT_REJECTED: " + (detail or "GraphQL error")
            )
        checkout = (item.get("data") or {}).get("checkoutSession")
        if not isinstance(checkout, dict):
            raise RuntimeError("IDENTITY_ELEVATION_CONTEXT_MISSING: checkoutSession")
        session_type = str(checkout.get("checkoutSessionType") or "")
        if session_type and session_type != "BILLING_WITHOUT_PURCHASE":
            raise RuntimeError("IDENTITY_ELEVATION_CONTEXT_TYPE_MISMATCH")
        return checkout

    def _phase2_create_account(self):
        result = super()._phase2_create_account()
        if not self.state.ec_token or not str(self.state.ec_token).startswith("EC-"):
            raise RuntimeError(
                "IDENTITY_ELEVATION_EC_MISSING: onboarding did not produce an EC checkout token"
            )
        checkout_result = self.session.graphql(
            "CheckoutSessionDataQuery",
            CHECKOUT_SESSION_DATA_QUERY,
            {"token": self.state.ec_token},
        )
        self._require_checkout_session(checkout_result)
        if not self.state.signup_url:
            self.state.signup_url = self._build_signup_url() if hasattr(self, "_build_signup_url") else ""
        if not self.state.content_identifier and hasattr(self, "_resolved_content_identifier"):
            try:
                self.state.content_identifier = self._resolved_content_identifier()
            except Exception:
                pass
        if not self.state.signup_url or not self.state.content_identifier:
            # Soft gate: PP-TH may resolve content_identifier later in phase3.
            logger.warning(
                "Identity-elevation signup context incomplete at phase2 "
                "(signup_url={} content_identifier={}); continuing",
                bool(self.state.signup_url),
                bool(self.state.content_identifier),
            )
        self.state.signup_context_ready = True
        logger.info("Identity-elevation EC/signup context validated")
        return result

    def _phase3_signup_and_2fa(self):
        if not self.state.ec_token or not str(self.state.ec_token).startswith("EC-"):
            raise RuntimeError("IDENTITY_ELEVATION_EC_MISSING: signup requires an EC checkout token")
        if not self.state.signup_context_ready:
            raise RuntimeError("IDENTITY_ELEVATION_SIGNUP_CONTEXT_NOT_READY")
        return super()._phase3_signup_and_2fa()

    @staticmethod
    def _funding_summary(checkout: dict) -> dict:
        options = checkout.get("fundingOptions")
        options = options if isinstance(options, dict) else {}
        selected = options.get("fundingInstrument")
        selected = selected if isinstance(selected, dict) else {}
        available_ids: set[str] = set()
        for plan in options.get("allPlans") or []:
            if not isinstance(plan, dict):
                continue
            for source in plan.get("fundingSources") or []:
                if not isinstance(source, dict):
                    continue
                instrument = source.get("fundingInstrument")
                instrument = instrument if isinstance(instrument, dict) else {}
                instrument_id = str(instrument.get("id") or "")
                if instrument_id:
                    available_ids.add(instrument_id)
        return {
            "selected": bool(selected.get("id")),
            "available": bool(available_ids),
            "available_count": len(available_ids),
        }

    def _query_elevated_context(self, token: str, referer: str) -> dict:
        headers = {
            "Referer": referer,
            "X-App-Name": "checkoutuinodeweb",
            "X-PayPal-Internal-EUAT": self.state.euat_token,
            "PayPal-Client-Context": token,
            "PayPal-Client-Metadata-Id": self.state.paypal_client_metadata_id,
            "X-Country": self.address.country,
            "X-Locale": self.locale,
        }
        result = self.session.graphql(
            "BuyerFundingContextQuery",
            BUYER_FUNDING_CONTEXT_QUERY,
            {"token": token},
            extra_headers=headers,
            endpoint="https://www.paypal.com/graphql/",
        )
        funding_obj = result[0] if isinstance(result, list) and result else result
        funding_obj = funding_obj if isinstance(funding_obj, dict) else {}
        funding_errors = [
            item for item in (funding_obj.get("errors") or [])
            if isinstance(item, dict)
        ]
        funding_error_messages = [
            str(item.get("message") or item.get("name") or "").strip()
            for item in funding_errors
            if str(item.get("message") or item.get("name") or "").strip()
        ]
        funding_checkpoints = sorted({
            str(checkpoint)
            for item in funding_errors
            for checkpoint in (item.get("checkpoints") or [])
            if str(checkpoint)
        })
        fatal_messages = {
            "PAYER_ACCOUNT_RESTRICTED",
            "PAYER_INVALID_FOR_PAYMENT",
            "TRANSACTION_REFUSED",
            "ACCOUNT_RESTRICTED",
            "ACCOUNT_LOCKED",
        }
        fatal_contingency = next(
            (message for message in funding_error_messages if message in fatal_messages),
            "",
        )

        def checkout_from(payload: dict) -> dict:
            data = payload.get("data")
            data = data if isinstance(data, dict) else {}
            checkout = data.get("checkoutSession")
            return checkout if isinstance(checkout, dict) else {}

        checkout = checkout_from(funding_obj)
        buyer = checkout.get("buyer")
        buyer = buyer if isinstance(buyer, dict) else {}

        if not str(buyer.get("userId") or ""):
            logger.warning(
                "Identity-elevation funding query requires buyer-only fallback: {}",
                json.dumps(sanitize_for_log(funding_obj), ensure_ascii=False)[:1000],
            )
            fallback = self.session.graphql(
                "BuyerContextQuery",
                BUYER_CONTEXT_QUERY,
                {"token": token},
                extra_headers=headers,
                endpoint="https://www.paypal.com/graphql/",
            )
            fallback_obj = fallback[0] if isinstance(fallback, list) and fallback else fallback
            fallback_obj = fallback_obj if isinstance(fallback_obj, dict) else {}
            checkout = checkout_from(fallback_obj)
            buyer = checkout.get("buyer")
            buyer = buyer if isinstance(buyer, dict) else {}

        auth = buyer.get("auth")
        auth = auth if isinstance(auth, dict) else {}
        refreshed_euat = str(auth.get("accessToken") or "")
        if refreshed_euat:
            self.session.set_euat_token(refreshed_euat)
        user_id = str(buyer.get("userId") or "")
        if user_id:
            self.state.user_id = user_id
        funding = self._funding_summary(checkout)
        return {
            "buyer_ready": bool(user_id and self.state.euat_token),
            "user_id": user_id,
            "auth_refreshed": bool(refreshed_euat),
            "funding_selected": funding["selected"],
            "funding_available": funding["available"],
            "funding_available_count": funding["available_count"],
            "funding_errors": funding_error_messages,
            "funding_checkpoints": funding_checkpoints,
            "fatal_contingency": fatal_contingency,
        }

    def _protocol_identity_elevation(self) -> dict:
        token = self.state.ec_token
        if not token or not str(token).startswith("EC-"):
            raise RuntimeError("IDENTITY_ELEVATION_EC_MISSING")
        if not self.state.euat_token:
            raise RuntimeError("IDENTITY_ELEVATION_EUAT_MISSING")
        if not self.state.signup_context_ready:
            raise RuntimeError("IDENTITY_ELEVATION_SIGNUP_CONTEXT_NOT_READY")

        logger.info("--- Identity elevation: guest checkout -> member checkout ---")
        self.session.set_euat_token(self.state.euat_token)
        if hasattr(self, "_ensure_euat_cookie"):
            try:
                self._ensure_euat_cookie()
            except Exception:
                pass

        signup_url = self.state.signup_url or (
            "https://www.paypal.com/checkoutweb/signup?" + urllib.parse.urlencode({
                "ssrt": self.state.ssrt,
                "ul": "1",
                "modxo_redirect_reason": "guest_user",
                "locale.x": self.locale,
                "country.x": self.address.country,
                "ba_token": self.ba_token,
                "token": token,
                "rcache": "1",
                "cookieBannerVariant": "hidden",
            })
        )
        saved_signup_euat = str(self.state.euat_token or "")

        if str(getattr(self.address, "country", "") or "").upper() in {"AE", "BA"}:
            logger.info("AE/BA pre-navigation member hydration started")
            immediate_context = self._query_elevated_context(token, signup_url)
            logger.info(
                "AE/BA pre-navigation hydration: buyer={} errors={} fatal={}",
                immediate_context["buyer_ready"],
                immediate_context["funding_errors"],
                immediate_context["fatal_contingency"] or "none",
            )
            if immediate_context["fatal_contingency"]:
                raise RuntimeError(
                    "IDENTITY_ELEVATION_PAYER_RESTRICTED: "
                    + immediate_context["fatal_contingency"]
                )
            if immediate_context["buyer_ready"]:
                self._ae_pre_hydrated = True
                self._buyer_context_bound = True
                self._last_elevation_context = immediate_context
                return immediate_context
            if saved_signup_euat:
                self.session.set_euat_token(saved_signup_euat)

        self.session.get(
            signup_url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": signup_url,
                "Upgrade-Insecure-Requests": "1",
            },
        )
        if (
            str(getattr(self.address, "country", "") or "").upper() in {"AE", "BA"}
            and saved_signup_euat
            and not self.state.euat_token
        ):
            logger.info("AE/BA signup navigation cleared EUAT; restoring signup access token")
            self.session.set_euat_token(saved_signup_euat)

        review_referer = (
            "https://www.paypal.com/webapps/hermes?"
            + urllib.parse.urlencode({
                "ssrt": self.state.ssrt,
                "ul": "1",
                "modxo_redirect_reason": "guest_user",
                "locale.x": self.locale,
                "country.x": self.address.country,
                "ba_token": self.ba_token,
                "token": token,
                "rcache": "1",
                "cookieBannerVariant": "hidden",
                "fromSignupLite": "true",
                "billingLite": "1",
            })
        )
        self._load_review_context(review_referer, signup_url)
        context = self._query_elevated_context(token, review_referer)
        logger.info(
            "Identity elevation context: buyer={} funding_selected={} funding_available={} count={} errors={} fatal={}",
            context["buyer_ready"],
            context["funding_selected"],
            context["funding_available"],
            context["funding_available_count"],
            context["funding_errors"],
            context["fatal_contingency"] or "none",
        )
        if context["fatal_contingency"]:
            raise RuntimeError(
                "IDENTITY_ELEVATION_PAYER_RESTRICTED: " + context["fatal_contingency"]
            )
        if not context["buyer_ready"]:
            raise RuntimeError(
                "IDENTITY_ELEVATION_FAILED: member identity was not attached to the EC checkout"
            )
        self._buyer_context_bound = True
        self._last_elevation_context = context
        return context

    def _elevate_guest_identity(self) -> None:
        """Override PP-TH simple elevate with protocol identity hydration."""
        context = self._protocol_identity_elevation()
        logger.info(
            "Identity elevation complete: buyer_ready={} user_id_present={}",
            context.get("buyer_ready"),
            bool(context.get("user_id")),
        )

    def _bind_buyer_to_current_ec(self) -> None:
        """Buyer already bound during protocol identity elevation."""
        if getattr(self, "_buyer_context_bound", False) and getattr(self, "_last_elevation_context", None):
            logger.info(
                "Buyer/EC already bound via identity elevation; skipping legacy bind helper"
            )
            return
        super()._bind_buyer_to_current_ec()

    def _phase4_authorize(self, skip_initial_hagrid: bool | None = None) -> dict:
        # Prefer skip when elevation already bound buyer.
        if skip_initial_hagrid is None and getattr(self, "_buyer_context_bound", False):
            skip_initial_hagrid = True
        try:
            if not getattr(self, "_last_elevation_context", None):
                context = self._protocol_identity_elevation()
            else:
                context = self._last_elevation_context
        except RuntimeError as exc:
            reason = str(exc)
            country = str(getattr(self.address, "country", "") or "").upper()
            ec_token = str(getattr(self.state, "ec_token", "") or "")

            if (
                country != "AE"
                or "IDENTITY_ELEVATION_PAYER_RESTRICTED" in reason
                or not ec_token.startswith("EC-")
            ):
                # If elevate_bind already ran elevation in run(), re-raise.
                # If phase4 is called standalone after elevate, re-raise hard errors.
                raise

            logger.warning(
                "AE identity elevation unavailable; using current ANONYMOUS EC session once: {}",
                reason,
            )
            strict_before = getattr(self, "_strict_buyer_context", True)
            self._strict_buyer_context = False
            try:
                result = super()._phase4_authorize(skip_initial_hagrid=skip_initial_hagrid)
            finally:
                self._strict_buyer_context = strict_before

            if isinstance(result, dict):
                result.setdefault("buyer_mode", "ae_anonymous_fallback")
                result.setdefault(
                    "identity_elevation",
                    {
                        "buyer_ready": False,
                        "anonymous_fallback": True,
                        "reason": reason,
                    },
                )
            return result

        result = super()._phase4_authorize(skip_initial_hagrid=True if skip_initial_hagrid is None else skip_initial_hagrid)
        if isinstance(result, dict):
            result.setdefault("buyer_mode", "identity_elevation")
            result.setdefault("identity_elevation", context)
        return result
