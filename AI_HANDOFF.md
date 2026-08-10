# AI Handoff — PP-TH- (PayPal Multi-Country BA)

> **Audience:** another coding agent continuing this repo.  
> **Repo:** https://github.com/suixin00001111/PP-TH-  
> **Docs updated:** 2026-08-10  
> **Current product facts (do not use older “Web locks Brazil trio only” notes):**  
> 1) 44 countries + curated `ADDRESS_POOLS`  
> 2) Online OSM address (`PAYPAL_ONLINE_ADDRESS`, default on) with local fallback  
> 3) Buyer modes: `legacy` | `elevate_bind` (`identity_elevation` alias) via `elevation_flow.py`  
> 4) Web **accepts** client fingerprint/DataDome/MTR choices (headless/roxy/protocol) — **not** force-locked to random/protocol only  
> 5) Server `deploy/install.sh` still seeds **pure-protocol** `.env` defaults  
> 6) Windows TLS CA mirror + proxy `require_proxy` only when user filled a proxy  
> **Language:** English for machine clarity; product UI/logs often Chinese.

Read this **before** changing flow, proxy, session, elevation, address generation, or web job ownership.

---

## 0. One-minute orientation

| Fact | Detail |
|------|--------|
| What it is | **Local** multi-country PayPal **Billing Agreement (BA)** pure-HTTP state machine + Web UI + CLI |
| What it is **not** | Not a clone of `pay.153.ink`; not a remote job platform client |
| Countries | **44** via `GET /api/regions` / `list_regions_public()` |
| Product line | **A-layer BA** Phase 0–4; optional B/C merchant chain (default **off**) |
| Buyer identity | `legacy` (default) or `elevate_bind` / aliases → `IdentityElevationPayPalFlow` |
| Address | OSM online → `ADDRESS_POOLS` → Faker (`paypal/online_address.py`, `oaipy_data.generate_address`) |
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
- Don’t re-introduce “create_job always overwrites risk knobs to Brazil lock” unless user asks.
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

2026-08-10 smoke (local): 44/44 construct; elevate job Phase0→2 fail clean; HTTP create maps `identity_elevation` → `elevate_bind`.

---

## 10. Recent history (do not casually revert)

| Theme | Notes |
|-------|--------|
| Windows runnable | `ssl_env`, direct when no filled proxy, device cookie |
| Brazil-public phase order | Phase1 before Phase2; dynamic ModXO preference |
| **Superseded** Web “Brazil lock only” (`b371986` era) | UI/create_job again allow headless/roxy; docs must not claim lock-only |
| Proxy diagnose accuracy | CA on probe; no false forbidden-IP |
| Identity elevation | `elevation_flow.py`, BUYER_* GraphQL, Web selection |
| Online address + 44 pools | `online_address.py`, expanded `ADDRESS_POOLS` |

---

## 11. Known limitations

- Live BA success rate = exit IP + token freshness + PayPal risk (not fully unit-testable).
- OSM timeouts slow address gen → set `PAYPAL_ONLINE_ADDRESS=0` for CI.
- elevate_bind **full** success needs real BA through Phase3–4.
- `flow.py` is huge; surgical edits only.
- CAPTCHA: manual/official; external solvers disabled.
- CentOS 7 headless may need pinned Playwright 1.30 (see `HANDOFF.md`).

---

## 12. Suggested next work

1. Real BA + residential E2E (especially elevate_bind).  
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
Address: OSM online (PAYPAL_ONLINE_ADDRESS) → ADDRESS_POOLS → Faker
Web: selectable risk engines (not force-locked); server .env often pure-protocol
Phase: 0→1→2→3→4; smoke fake BA → Phase2 fail OK
Windows: ssl_env CA; require_proxy only if proxy filled
Phone CC must match country on create_job
Do not commit .env. Do not invent EC for fake BA.
```
