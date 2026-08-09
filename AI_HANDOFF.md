# AI Handoff — PP-TH- (PayPal Multi-Country BA)

> **Audience:** another coding agent continuing this repo.  
> **Repo:** https://github.com/suixin00001111/PP-TH-  
> **Docs updated:** 2026-08-10  
> **Recent themes:** (1) Windows runnable (TLS CA, proxy direct, device cookie); (2) Brazil-public protocol order (Phase1 before Phase2, dynamic ModXO ids).  
> **Language:** English for machine clarity; product UI/logs often Chinese.

Read this **before** changing flow, proxy, session, or web job ownership. Do not treat public SaaS sites as source-of-truth code; this tree is the implementation.

---

## 0. One-minute orientation

| Fact | Detail |
|------|--------|
| What it is | **Local** multi-country PayPal **Billing Agreement (BA)** pure-HTTP state machine + Web UI + CLI |
| What it is **not** | Not a clone of `pay.153.ink` / private pay153 deploy; not a remote job platform client |
| Product line | **A-layer BA** Phase 0–4; optional B/C merchant chain (default **off** in Web) |
| Default runtime | Pure protocol: `fingerprint=random`, `datadome=protocol`, `mtr=python_generated` |
| Phase order | **0 → 1 (risk beacons) → 2 → 3 → 4** (aligned with Brazil public package) |
| ModXO action ids | **Dynamic-first** (`PAYPAL_MODXO_STATIC_ACTION_IDS=0`); static capture only as opt-in fallback |
| Entry points | `web.py` (HTTP UI/API), `main.py` (CLI), `start.bat` / `start.sh` |
| Core engine | `paypal/flow.py` → `PayPalFlow` (very large; TH-shaped multi-country protocol) |
| Success criteria (local) | Install deps → Web up → `/api/health` → create job → Phase 0 page load → Phase 2 actions against PayPal |
| Full BA success needs | **Real unexpired BA token** + **target-country residential proxy** (or working TUN) + phone/OTP (manual or SMSBower) |

Fake tokens (`BA-TEST…`, `BA-ABCDEF…`) are only for **smoke**. Expect PayPal `INVALID_TOKEN` / `generic-error` / `authchallenge` / “no EC token” — that is **not** “project broken”. A healthy smoke path logs Phase0 page 200 → Phase1 risk beacons → Phase2 server actions, then fails on token/risk.

---

## 1. Do / Don’t (agent rules)

### Do

- Keep secrets out of git: `.env`, real BA, proxy user/pass, Roxy keys, SMS API keys, cookies, HAR.
- Prefer pure-protocol defaults unless user explicitly wants headless/Roxy.
- When debugging “can’t run”, check in order: **SSL CA path → proxy resolve → device cookie → BA format → real network risk**.
- Run tests after proxy/session/ssl/web helper changes:  
  `python -m pytest tests -q` or `python -m unittest discover -s tests -q`
- On Windows with non-ASCII home paths, always go through `paypal.ssl_env.ensure_ssl_cert_env` before HTTP clients.

### Don’t

- Don’t hard-require a working system/Clash proxy when the user left proxy empty / `proxy_enabled=false`.
- Don’t commit `.env` (ignored; only `.env.example`).
- Don’t re-enable external CAPTCHA solvers if code path says manual/official only.
- Don’t assume `X-Device-Id` header alone owns jobs — ownership is **`paypal_web_device_id` cookie** (see §5).
- Don’t “fix” fake-BA Phase2 failures by inventing EC tokens.
- Don’t force-push or rewrite published history unless user explicitly asks.

---

## 2. Architecture map

```text
web.py / main.py
  │ ensure_ssl_cert_env()          # ASCII CA for curl_cffi on Chinese Windows paths
  ├─ generate_oaipy_profile()      # Faker locale per country
  ├─ resolve_outbound_proxy()      # filled → optional system → direct
  └─ PayPalFlow.run()
        Phase0  GET agreements/approve?ba_token=…  (cookies, DataDome edge, ModXO action ids)
        Phase1  fingerprint + Tealeaf + analytics on /pay (Brazil public order; was missing)
        Phase2  ModXO server actions → EC token / signup
        Phase3  OTP (Griffin / 2FA phone confirm)
        Phase4  AuthorizeBillingAgreement → return_url / BA id
        [optional] merchant B/C if CONTINUE_MERCHANT
```

**Brazil public reference tree** (local peer, not a dependency):
`E:\桌面\巴西paypal协议 (1)\paypal-pay-public-nocdk` — smaller BR-only package.
Useful borrow points already applied: Phase1 before Phase2, dynamic ModXO ids default,
`trust_env=False`, proxy pool toggle, compact Web OTP UX. Do **not** copy BR-only CPF
or hard-coded `X-Country: BR` into multi-country paths.

### Important modules

| Path | Role |
|------|------|
| `paypal/flow.py` | Main BA state machine (`PayPalFlow`) |
| `paypal/flow_legacy_multicountry.py` | Legacy multi-country helpers / BA regex |
| `paypal/session.py` | HTTP client: **curl_cffi preferred**, httpx fallback; CA path; proxy URL |
| `paypal/ssl_env.py` | Mirror `certifi` PEM to `C:\ProgramData\PP-TH\cacert.pem` (ASCII) |
| `paypal/proxy.py` | Parse proxy strings, probe, `resolve_outbound_proxy`, system Clash ports |
| `paypal/regions.py` / `region_matrix.py` / `country_profiles.py` | Country protocol context |
| `paypal/oaipy_data.py` | User/card/address generation |
| `paypal/runtime_config.py` / `runtime_bridge.py` | Map coarse runtime → fine risk knobs |
| `paypal/graphql.py` | Checkout / Griffin / OTP / signup / authorize queries |
| `paypal/smsbower.py` | Optional auto OTP provider |
| `paypal/local_headless.py` / `roxy_fingerprint.py` | Optional browser assist |
| `web.py` | Threading HTTP server, jobs, device cookie, static UI |
| `web_static/` | `index.html` + `app.js` + `app.css` |
| `config.py` | Defaults (no secrets); env overrides via `.env` loaders elsewhere |
| `PROTOCOL_CHAIN.md` | Phase narrative (TH reference) |
| `PROXY.md` | cliproxy / TUN / system proxy ops notes |
| `SETUP.md` / `SANITIZATION.md` | Setup + sanitization policy |

---

## 3. Runtime & env knobs

Copy `.env.example` → `.env` (gitignored).

| Variable | Meaning (typical default) |
|----------|---------------------------|
| `PAYPAL_RUNTIME_MODE` | `protocol` \| `headless` \| `auto` \| `roxy` → **protocol** |
| `PAYPAL_FINGERPRINT_SOURCE` | `random` (default pure protocol) |
| `PAYPAL_DATADOME_MODE` | `protocol` |
| `PAYPAL_MTR_RUNTIME` | `python_generated` |
| `PAYPAL_PROXY_ENABLED` | `0` |
| `PAYPAL_USE_SYSTEM_PROXY` | `0` — **do not** probe half-broken Clash when unset |
| `PAYPAL_PROXY_URL` / `PAYPAL_PROXY_POOL` | Explicit proxies |
| `PAYPAL_CONTINUE_MERCHANT` | `0` — Web forces A-layer only |
| `SMSBOWER_*` | Auto OTP (off by default) |
| `PAYPAL_ROXY_*` | Roxy Local API (optional) |
| `PAYPAL_WEB_*` | Job limits, OTP timeout, debug logs |

Web job create also accepts JSON fine knobs; Web profile is forced **real** and **continue_merchant=False** in `create_job`.

---

## 4. Proxy resolution contract (critical)

Implemented in `paypal/proxy.py` → `resolve_outbound_proxy(filled_raw, require_proxy=…, allow_system_fallback=…)`.

**Strategy (current):**

1. If user filled a proxy URL → try it first (may auto-upgrade residential to `socks5h`).
2. System/local assist (Clash `127.0.0.1:7897` etc.) only when:
   - `require_proxy` is true, **or**
   - filled raw present, **or**
   - `PAYPAL_USE_SYSTEM_PROXY` / `config.USE_SYSTEM_PROXY` is true.
3. If nothing works and `require_proxy=False` → **`(None, "", 0, "direct")`** — job continues on machine default route.
4. If `require_proxy=True` and nothing works → raise Chinese actionable `ValueError`.

**Web runner** (`web.py` job thread):

- `require_proxy = bool(filled_raw) or (proxy enabled with entry)`  
- Empty form + proxy off → **must not** hard-fail on dead local 7897.

**Historical bug:** probing broken system proxy on every job caused multi-second SSL timeouts and “project won’t run”. Fixed; tests in `tests/test_resolve_outbound_proxy.py`.

---

## 5. Web server & job ownership

### Start

```text
python web.py --host 127.0.0.1 --port 8080
# or start.bat (pip install, copy .env.example, ensure_ssl_cert_env, port 8080)
```

### APIs

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/health` | `{ok, time}` |
| GET | `/api/regions` | Country matrix |
| GET | `/api/runtime` | Default risk modes |
| GET/POST | `/api/jobs` | List / create |
| GET | `/api/jobs/{id}` | Detail + logs (owner only) |
| POST | `/api/jobs/{id}/otp` | Submit OTP / prompt |
| POST | `/api/proxy/test` | Connectivity probe |
| POST | `/api/roxy/test` | Roxy Local API probe |

### Device cookie (easy to break jobs)

- Cookie name: `paypal_web_device_id` (HttpOnly, SameSite=Strict).
- Job `owner_device_id` is set from cookie on create.
- GET job filters by **same device id**.
- Browser `fetch` uses same-origin cookies by default → OK in UI.
- Raw API clients **without** cookie jar see empty job list / 404 on detail.
- **Fix already applied:** serving `index.html` also issues Set-Cookie via `get_device_id()`.

### BA token validation

- Regex: `^BA-[A-Za-z0-9]{8,80}$` (`web.py` / flow legacy).
- Smoke-safe example: `BA-ABCDEFGH12345678` (format OK, PayPal will still reject later).

---

## 6. TLS / curl_cffi on Windows (curl 77)

**Problem:** `certifi` under `C:\Users\<中文>\...` → libcurl **error 77** “error adding trust anchors”.

**Fix:** `paypal/ssl_env.py` → `ensure_ssl_cert_env()`:

- Copies CA to ASCII path preference: `%PROGRAMDATA%\PP-TH\cacert.pem`, then Public, then temp.
- Sets `SSL_CERT_FILE` / `CURL_CA_BUNDLE` / related env.
- Called early from `web.py`, `main.py`, `start.bat`.

`paypal/session.py` logs something like:

```text
HTTP client: curl_cffi (chrome) ca=C:\ProgramData\PP-TH\cacert.pem
```

If curl still fails, session may fall back to httpx — prefer keeping curl_cffi working for TLS fingerprint.

Tests: `tests/test_ssl_env.py`.

---

## 7. How far a smoke job should go

With **direct** network + **fake BA** + protocol modes (observed on maintainer Windows):

1. Proxy resolve → `direct` (fast if system assist off).
2. Generate TH/JP/… profile.
3. **Phase 0:** `Page loaded: 200`, ModXO action ids (often static), DataDome cookie may appear.
4. **Phase 2:** Pay_With_Card / Tealeaf / DFP / Continue_To_Payment.
5. Fail with one of:
   - `authchallenge` / `hcaptchapassive` (risk; needs better exit IP / real session quality),
   - `no valid EC token` (invalid/expired BA or ModXO no redirect).

**That path = engine runnable.**  
**OTP / authorize = needs real BA + good proxy + phone.**

Do not regress Phase0 page load while “optimizing” proxy to always fail closed.

---

## 8. Relation to public pay.153 / private peers

| | Public/private SaaS | This repo |
|--|---------------------|-----------|
| Hosting | Their servers + pools | Local only |
| API | Their `/paypal-pay/api/jobs` etc. | Local `/api/jobs` |
| Code | Closed | Open tree here |
| Goal alignment | Same **BA product idea** | Independent protocol implementation |

`PROTOCOL_CHAIN.md` §0 is **contrast only** — not a dependency.

User may compare UX to `pay.153.ink` or hosts like `107.x:18096`; implement features **in this codebase**, don’t scrape their backend as a requirement.

---

## 9. Tests & verification checklist

```powershell
cd <repo>
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests -q
# expect ~65+ passing after ssl/proxy tests added

.\.venv\Scripts\python.exe web.py --host 127.0.0.1 --port 18080
# GET /api/health → 200
# POST /api/jobs with cookie jar + valid BA format + proxy_enabled false
# Poll until failed/success; logs must show Phase 0 page load without curl 77
```

Key test files:

- `tests/test_resolve_outbound_proxy.py` — direct path / require_proxy
- `tests/test_ssl_env.py` — CA mirror
- `tests/test_flow_state_guards.py` — protocol continue guards (DataDome expectations aligned to continue)
- `tests/test_web_helpers.py` — job dict / helpers
- Region/profile/session authchallenge tests — don’t loosen without reason

---

## 10. Recent fixes (do not revert casually)

### A. Windows runnable (`7f1e4c1` family)

1. **`paypal/ssl_env.py`** — curl 77 / non-ASCII path.
2. **`paypal/session.py`** — mirrored CA; curl→httpx resilience.
3. **`paypal/proxy.py`** — `require_proxy=False` → direct; skip system probe when assist disabled.
4. **`web.py`** — require_proxy only when user asked; index.html device cookie; early `ensure_ssl_cert_env`.
5. **`start.bat`** — venv bootstrap; `.env.example` copy; CA preflight.
6. **`main.py`** — early `ensure_ssl_cert_env`.
7. Tests: `test_resolve_outbound_proxy.py`, `test_ssl_env.py`, flow guard updates.

### B. Brazil-public protocol alignment (`e7f7e1a` family)

1. **`PayPalFlow.run`**: Phase0 → **Phase1 risk beacons** → Phase2 (was skipping Phase1).
2. **`_phase1_risk_controls`**: fingerprint + Tealeaf + analytics on `/pay` before ModXO.
3. **ModXO ids**: default `PAYPAL_MODXO_STATIC_ACTION_IDS=0` (dynamic-first); core pair = create-account + create-user (Brazil-style); emergency-static only if scan finds **nothing**.
4. **Phone CC** on Continue_To_Payment: protocol `phone_cc`, not hard-coded `+55`.
5. Docs: `PROTOCOL_CHAIN.md`, `.env.example`, this handoff.

---

## 11. Known limitations / open risks

- Full live BA success rate depends on **exit IP quality**, token freshness, and PayPal risk — not unit-testable end-to-end here.
- Half-open Windows “系统代理” without TUN still confuses humans; code should prefer direct when not required.
- `flow.py` is huge (~8k+ lines); surgical edits only; prefer existing helpers.
- Static ModXO action ids can go stale → code refreshes from JS chunks; watch `continue_to_payment_no_redirect`.
- CAPTCHA: manual/official path; external solvers disabled by design in observed logs.
- Python 3.14 was used in one maintainer env; README says 3.10+ — stick to supported libs (`curl_cffi`, httpx).

---

## 12. Suggested next work (if user asks)

Priority order usually:

1. Real BA + residential proxy E2E to OTP.
2. Clearer Web error copy for authchallenge vs invalid BA vs proxy.
3. Optional: document port 8080 vs debug 18080.
4. Keep pure-protocol default; only deepen headless/Roxy if user needs risk bypass and has Roxy key.
5. Never expand scope into checkout-only rails unless requested (different product).

---

## 13. File touch guide (where to edit)

| User request | Touch first |
|--------------|-------------|
| “Won’t start / curl 77” | `ssl_env.py`, `session.py`, `start.bat` |
| “Proxy blocks all jobs” | `proxy.py` `resolve_outbound_proxy`, `web.py` runner |
| “Job not found in UI” | `web.py` cookie + `get_device_id` / `get_authorized_job` |
| “Wrong country data” | `regions.py`, `oaipy_data.py`, `country_profiles.py` |
| “Phase X protocol” | `flow.py` (careful), `graphql.py`, `PROTOCOL_CHAIN.md` |
| “OTP auto” | `smsbower.py`, Web form flags |
| “UI only” | `web_static/app.js`, `app.css`, `index.html` |

---

## 14. Handoff message template (paste to next agent)

```text
Repo: https://github.com/suixin00001111/PP-TH-
Read: AI_HANDOFF.md, README.md, PROTOCOL_CHAIN.md, PROXY.md, SETUP.md
Stack: local multi-country PayPal BA pure HTTP + web.py
Defaults: protocol/random/python_generated; Phase0→1→2→3→4; ModXO dynamic-first
Windows: ssl_env CA mirror, direct proxy when unset, device cookie on index
Smoke: health + fake BA → Phase0/1/2 then INVALID_TOKEN or authchallenge (OK)
Do not require system Clash for no-proxy jobs. Do not commit .env.
Live success: real BA + residential proxy + OTP. Brazil public is reference order only.
```

---

## 15. Security note for agents

- Redact tokens in logs (already partially done).
- Never print full proxy credentials in handoff replies.
- If user pastes live BA/proxy in chat, use for local run only; don’t put into committed docs or tests.

---

*End of handoff. Update this file when you change proxy/ssl/web ownership contracts or Phase success criteria.*
