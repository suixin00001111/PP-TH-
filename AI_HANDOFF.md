# AI Handoff — PP-TH- (PayPal Multi-Country BA)

> **Audience:** another coding agent continuing this repo.  
> **Repo:** https://github.com/suixin00001111/PP-TH-  
> **Docs updated:** 2026-08-13  
> **Current product facts:**  
> 1) 44 countries + curated `ADDRESS_POOLS`  
> 2) **Address is online-first** (OSM Nominatim/Overpass + cache); name/phone/card/KYC IDs are **local-generated** — not full online identity scrape  
> 3) Buyer modes: `legacy` | `elevate_bind` (`identity_elevation` alias) via `elevation_flow.py`  
> 4) Web **accepts** client fingerprint/DataDome/MTR choices (headless/roxy/protocol)  
> 5) Server `deploy/install.sh` seeds **pure-protocol** `.env` defaults  
> 6) Windows TLS CA mirror + proxy `require_proxy` only when user filled a proxy  
> 7) TH-class KYC (nationality + NATIONAL_ID + residentialAddress) hardened 2026-08-12 — do not regress  
> **Language:** English for machine clarity; product UI/logs often Chinese.  
> Describe this repo on its own terms only.  
> **Community (human support):** QQ group **`1098798456`** — usage / deploy / proxy troubleshooting; never paste live secrets.  
> **Primary protocol reference (elevation + multi-country):** `paypal-agreement-protocol-main` (`identity_elevation`).  
> **BR-only package `openai-paypal`:** CPF/locale reference only — do **not** wholesale-align (keeps phone-confirm / TH KYC guards).

Read this **before** changing flow, proxy, session, elevation, address generation, or web job ownership.

---

## 0. One-minute orientation

| Fact | Detail |
|------|--------|
| What it is | **Local** multi-country PayPal **Billing Agreement (BA)** pure-HTTP state machine + Web UI + CLI |
| What it is **not** | Not a remote job-platform client; all logic runs in this tree |
| Countries | **44** via `GET /api/regions` / `list_regions_public()` |
| Product line | **A-layer BA** Phase 0–4; optional B/C merchant chain (default **off**) |
| Buyer identity | `legacy` (default) or `elevate_bind` / aliases → `IdentityElevationPayPalFlow` |
| Address | **Online OSM first** (default on) → `ADDRESS_POOLS` → Faker (`online_address.py`, `oaipy_data.generate_address`) |
| Other PII | Local generators only (names, phones, cards, CPF/NATIONAL_ID algorithms) |
| Elevate reference | Ported from `paypal-agreement-protocol-main` elevation_flow (~same Guest→Member + BuyerFunding path) |
| Web risk knobs | **Selectable** in UI + honored by `create_job` (`random`/`headless`/`roxy`, etc.) |
| API runtime `default` | Documents pure-protocol recommendation: random + protocol + python_generated |
| Phase order | **0 → 1 (risk beacons) → 2 → 3 → 4** |
| Proxy hard-fail | **Only when user filled a proxy URL** (`require_proxy=bool(filled_raw)`); empty → direct |
| Entry points | `web.py`, `main.py`, `start.bat` / `start.sh` |
| Core engine | `paypal/flow.py` → `PayPalFlow`; elevation subclass in `elevation_flow.py` |
| Smoke success | Web up → health → create job (fake BA, proxy off) → Phase0/1/2 → fail without EC (**not hung**) |
| Full BA success | Real BA + target-country residential proxy (or TUN) + phone/OTP |

Fake tokens (`BA-TEST…`) are **smoke only**. Expect `INVALID_TOKEN` / `generic-error` / `authchallenge` / “no EC token”.

---

## 1. Do / Don’t (agent rules)

### Do

- Keep secrets out of git: `.env`, real BA, proxy creds, Roxy/SMS keys, cookies, HAR.
- Prefer pure-protocol for server multi-tenant unless user has Playwright/Roxy.
- Debug order: **SSL CA → proxy resolve → device cookie → phone/country match → BA format → network risk**.
- After proxy/session/ssl/web/elevation/address changes, run:  
  `PAYPAL_ONLINE_ADDRESS=0 python -m unittest discover -s tests -q`
- On Windows non-ASCII home paths, call `paypal.ssl_env.ensure_ssl_cert_env` before HTTP clients.
- Keep `flow.py` ↔ `web.py` ↔ `web_static` buyer-mode aliases in sync.
- Extend `ADDRESS_POOLS` instead of relying on Faker junk for new countries.

### Don’t

- Don’t hard-require system/Clash proxy when proxy is empty / disabled.
- Don’t force-overwrite client risk knobs in `create_job` unless the user explicitly asks for a lock-down.
- Don’t commit `.env`.
- Don’t re-enable external CAPTCHA solvers if code says manual/official only.
- Don’t assume `X-Device-Id` owns jobs — ownership is cookie **`paypal_web_device_id`**.
- Don’t “fix” fake-BA Phase2 by inventing EC tokens.
- Don’t force-push published history unless user asks.

---

## 2. Architecture map

```text
web.py / main.py
  │ ensure_ssl_cert_env()
  ├─ generate_oaipy_profile() / generate_address()
  │     online OSM? → ADDRESS_POOLS → Faker
  ├─ resolve_outbound_proxy()   # filled → optional system → direct
  └─ PayPalFlow  OR  IdentityElevationPayPalFlow / WebElevationPayPalFlow
        Phase0  agreements/approve
        Phase1  fingerprint + Tealeaf + analytics on /pay
        Phase2  ModXO → EC / signup
        Phase3  OTP + SignUpNewMember
        Phase4  authorize
                elevate_bind: elevate guest → bind EC → authorize
        [optional] merchant B/C if CONTINUE_MERCHANT
```

### Important modules

| Path | Role |
|------|------|
| `paypal/flow.py` | Main BA state machine |
| `paypal/elevation_flow.py` | Guest elevate + bind EC + buyer GraphQL hydration |
| `paypal/online_address.py` | Nominatim/Overpass + cache; `PAYPAL_ONLINE_ADDRESS` |
| `paypal/country_profiles.py` | **44** `ADDRESS_POOLS`, BINs, phone rules |
| `paypal/oaipy_data.py` | Profile generation entrypoints |
| `paypal/session.py` | curl_cffi preferred; CA; proxy; `set_euat_token` |
| `paypal/ssl_env.py` | ASCII CA mirror for Windows curl 77 |
| `paypal/proxy.py` | Parse/probe/`resolve_outbound_proxy` |
| `paypal/graphql.py` | Checkout/Griffin/OTP/signup/authorize + BUYER_* |
| `paypal/local_headless.py` / `roxy_fingerprint.py` | Optional browser assist |
| `web.py` | Jobs, device cookie, static UI, elevation selection |
| `web_static/` | Form: risk engines + buyer mode |
| `deploy/install.sh` | VPS install; pure-protocol `.env` seeds |
| Docs | `README.md`, `SETUP.md`, `PROXY.md`, `DEPLOY.md`, `PROTOCOL_CHAIN.md`, `HANDOFF.md` |

---

## 3. Runtime & env knobs

Copy `.env.example` → `.env`.

| Variable | Typical meaning |
|----------|-----------------|
| `PAYPAL_RUNTIME_MODE` | protocol \| headless \| auto \| roxy |
| `PAYPAL_FINGERPRINT_SOURCE` | random / headless / roxy … |
| `PAYPAL_DATADOME_MODE` | protocol / headless / roxy … |
| `PAYPAL_MTR_RUNTIME` | python_generated / headless / roxy … |
| `PAYPAL_ONLINE_ADDRESS` | `1` online OSM (default); `0` local pools only |
| `PAYPAL_PROXY_*` / `PAYPAL_USE_SYSTEM_PROXY` | Outbound |
| `PAYPAL_CONTINUE_MERCHANT` | `0` Web A-only |
| `SMSBOWER_*` / `PAYPAL_ROXY_*` / `PAYPAL_WEB_*` | Optional |

`create_job` honors JSON fine knobs from the client (after validation).  
Server install forces pure-protocol **defaults in `.env`**, not a hard UI lock.

---

## 4. Proxy resolution contract (critical)

`paypal/proxy.py` → `resolve_outbound_proxy(...)`.

1. User-filled proxy first (may auto-upgrade residential to `socks5h`).
2. System/Clash assist only when required / filled / `USE_SYSTEM_PROXY`.
3. `require_proxy=False` and nothing works → **direct** (do not hang on dead 7897).
4. `require_proxy=True` and fail → actionable Chinese `ValueError`.

Tests: `tests/test_resolve_outbound_proxy.py`.

---

## 5. Web server & job ownership

```text
python web.py --host 127.0.0.1 --port 8080
```

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/health` | `{ok, time}` |
| GET | `/api/regions` | 44 countries |
| GET | `/api/runtime` | defaults + choice lists + **buyer_identity_modes** |
| GET/POST | `/api/jobs` | list/create |
| GET | `/api/jobs/{id}` | owner only |
| POST | `/api/jobs/{id}/otp` | OTP |
| POST | `/api/proxy/test` | proxy probe |
| POST | `/api/roxy/test` | optional |

- Cookie: `paypal_web_device_id` (HttpOnly). Raw clients without cookie jar see empty lists / 404.
- BA regex ≈ `^BA-[A-Za-z0-9]{8,80}$`.
- **Phone country calling code must match `country`** or create returns **400**.

Buyer mode aliases (web + flow): map `identity_elevation`, `elevate`, `v2`, … → `elevate_bind`.

When mode is elevate, runner constructs **`WebElevationPayPalFlow`**.

---

## 6. TLS / curl_cffi on Windows (curl 77)

`paypal/ssl_env.py` mirrors certifi PEM to ASCII paths (`%PROGRAMDATA%\PP-TH\cacert.pem`, …).  
Called from `web.py`, `main.py`, `start.bat`. Tests: `tests/test_ssl_env.py`.

---

## 7. Smoke expectations

Direct + fake BA + protocol (or headless if installed):

1. Proxy → direct (if empty).
2. Profile for selected country (pool/OSM address).
3. Phase0 page load; Phase1 beacons; Phase2 actions.
4. Fail: authchallenge / no EC / generic-error.

**Engine healthy if it reaches that fail without hanging.**  
OTP/authorize needs real BA + good exit IP + phone.

---

## 8. Relation to public SaaS

Independent local implementation. `PROTOCOL_CHAIN.md` §0 is contrast only.  
Implement features **in this tree**; do not scrape third-party backends as source of truth.

---

## 9. Tests & checklist

```powershell
$env:PAYPAL_ONLINE_ADDRESS = "0"
python -m unittest discover -s tests -q
```

Key files:

- `test_buyer_identity_mode.py` — elevate routing / aliases  
- `test_online_address.py` — env gate / fallbacks  
- `test_country_profiles_fidelity.py` — pools  
- `test_resolve_outbound_proxy.py`, `test_ssl_env.py`  
- `test_web_helpers.py`, `test_flow_state_guards.py`, `test_regions_phone.py`
- `test_th_signup_kyc.py`, `test_opaque_onboard_failure.py`

2026-08-10 smoke (local): 44/44 construct; elevate job Phase0→2 fail clean; HTTP create maps `identity_elevation` → `elevate_bind`.

**2026-08-12 verification (VPS + local):**

| Check | Result |
|-------|--------|
| `test_buyer_identity_mode` | 7 passed (elevate path + aliases + elevation helpers) |
| `test_th_signup_kyc` | 6 passed |
| VPS bare-user SignUp vars | `ASSERT_PASS` nationality TH + 13-digit NATIONAL_ID + residential |
| `GET /api/runtime` | exposes `legacy` + `elevate_bind` |
| API bad mode | rejects `not_a_real_mode` |
| API alias `identity_elevation` | normalizes to `elevate_bind`; job log `buyer=elevate_bind` |
| Online address on VPS | default enabled; logs `Online address resolved for TH/US/ID` |
| Live full BA / full elevate | **Blocked** without fresh BA (stale tokens die at Phase2 “no EC token”; proxy TLS flaky) |
| Stale `paypal_signup_variables_last.json` | mtime not updated until a job reaches SignUp — ignore old `has_identity=false` as regression |

**2026-08-13:** local + VPS 44-country offline matrix **44/44**. Identity markets: TH(13) ID(16) PH(16) TW(10) AE(15) BR CPF(11). This commit is the first push of KYC harden to GitHub (`origin/main` was still 2026-08-11 OTP-only). Live jobs still die at Phase2 without a fresh BA (fake token / hCaptcha / proxy TLS) — not a missing-KYC regression.

---

## 10. Recent history (do not casually revert)

| Theme | Notes |
|-------|--------|
| Windows runnable | `ssl_env`, direct when no filled proxy, device cookie |
| Phase order | Phase1 risk beacons before Phase2; dynamic ModXO preference |
| Web risk knobs | Selectable headless/roxy/protocol; server `.env` may default pure-protocol |
| Proxy diagnose accuracy | CA on probe; no false forbidden-IP |
| Identity elevation | `elevation_flow.py`, BUYER_* GraphQL, Web selection (from protocol-main) |
| Online address + 44 pools | `online_address.py`, expanded `ADDRESS_POOLS` |
| TH KYC (2026-08-12) | `_ensure_user_kyc_fields`, hard assert, truthful diag flags, house-first line1 |

---

## 11. Known limitations

- Live BA success rate = exit IP + token freshness + PayPal risk (not fully unit-testable).
- OSM timeouts slow address gen → set `PAYPAL_ONLINE_ADDRESS=0` for CI.
- elevate_bind **full** success needs real BA through Phase3–4; mode routing is already verified.
- `flow.py` is huge; surgical edits only.
- CAPTCHA: manual/official; external solvers disabled.
- CentOS 7 headless may need pinned Playwright 1.30 (see `HANDOFF.md`).
- Proxy country filter may drop cliproxy nodes whose exit country ≠ form country.
- Signup diag JSON is **last successful write** only — no SignUp ⇒ stale snapshot.

---

## 12. Suggested next work

1. Fresh BA + residential E2E (legacy KYC path **and** elevate_bind through Guest elevate).  
2. Clearer Web copy for authchallenge vs invalid BA vs proxy.  
3. Optional server Playwright install path if multi-tenant wants headless.  
4. Keep docs/code in sync when changing Web defaults.

---

## 13. File touch guide

| User request | Touch first |
|--------------|-------------|
| curl 77 / won’t start | `ssl_env.py`, `session.py`, `start.bat` |
| Proxy blocks jobs | `proxy.py`, `web.py` runner |
| Job not found | device cookie / `get_authorized_job` |
| Bad address / country data | `online_address.py`, `country_profiles.py`, `oaipy_data.py` |
| elevate_bind | `elevation_flow.py`, `graphql.py`, `web.py`, `flow.py` normalize |
| Phase protocol | `flow.py` (careful), `graphql.py`, `PROTOCOL_CHAIN.md` |
| UI | `web_static/*` (+ bump `?v=` cache if present) |
| Deploy | `deploy/install.sh`, `DEPLOY.md` |

---

## 14. Handoff blurb (paste to next agent)

```text
Repo: https://github.com/suixin00001111/PP-TH-
Read: AI_HANDOFF.md, README.md, HANDOFF.md, PROTOCOL_CHAIN.md, PROXY.md, SETUP.md, DEPLOY.md
Stack: local 44-country PayPal BA pure HTTP + web.py
Buyer: legacy | elevate_bind (elevation_flow.py); alias identity_elevation
  elevate reference = paypal-agreement-protocol-main (not openai-BR wholesale)
Address: ONLINE OSM first (default) → ADDRESS_POOLS → Faker; other PII local
TH KYC: nationality + NATIONAL_ID + residential — hardened 2026-08-12
Web: selectable risk engines (not force-locked); server .env often pure-protocol
Phase: 0→1→2→3→4; smoke fake BA → Phase2 fail OK
Live E2E needs fresh BA + country-matched residential proxy + OTP
Windows: ssl_env CA; require_proxy only if proxy filled
Phone CC must match country on create_job
Do not commit .env. Do not invent EC for fake BA.
```
