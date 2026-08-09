# PayPal 全协议链路（本地纯 HTTP · 多国）

> 流程架子以泰国为参考；运行时按所选国家绑定 locale / 区号 / 资料。  
> 阶段顺序已对齐巴西公开包 `paypal-pay-public-nocdk`（Phase1 在 Phase2 前）。  
> 更新：2026-08。

## 0. pay.153 远端（对照，非本包依赖）

```text
UI country=TH
  POST /paypal-pay/api/jobs
    paypal_url | BA-...
    phone = +66...
    country = TH
    proxies = TH 出口池
  → Phase0..4 / awaiting_otp / awaiting_captcha
  → completed + result.return_url
```

## 1. 本包本地链路（对齐巴西公开包阶段顺序）

```text
main.py / web.py
  → ensure_ssl_cert_env()          # Windows 中文路径 CA
  → resolve_outbound_proxy()       # 填代理优先；未填可直连
  → generate_user/card/address (country pools)
  → PayPalFlow.run()
      Phase0: GET /agreements/approve?ba_token=BA-...
              follow redirects, extract ssrt / cookies / DataDome 判定
              ModXO Next-Action ids: live HTML/JS scan first
              (PAYPAL_MODXO_STATIC_ACTION_IDS=0 默认；扫空才 emergency-static)
      Phase1: FraudNet fingerprint + Tealeaf + analytics on /pay
              ★ 必须在 Phase2 之前（巴西公开包同序；曾漏跑）
      Phase2: ModXO Server Action Pay_With_Card / Continue_To_Payment
              → onboardingRedirectUrl / EC token / signup URL
      Phase3: GriffinMetadata(country/lang)
              InitiateRiskBasedTwoFactorPhoneConfirmation
              ConfirmRiskBasedTwoFactorPhoneConfirmation (OTP)
              SignUpNewMemberMutation
      Phase4: AuthorizeBillingAgreement → return_url / BA id
```

### 冒烟判定（假 BA）

| 日志 | 含义 |
|------|------|
| `Page loaded: 200` | Phase0 出站与 TLS 正常 |
| `Phase 1: Risk control signals` / `Risk control signals sent` | Phase1 已跑 |
| `Phase 2: Create account flow` | 进入 ModXO |
| `INVALID_TOKEN` / `generic-error` / `no valid EC token` / `authchallenge` | 假 token 或风控，**链路已通** |

## 2. 关键 GraphQL / HTTP

与巴西包共用 `paypal/graphql.py`：

- `CheckoutSessionDataQuery`
- `GriffinMetadataQuery`（countryCode=TH, languageCode=th）
- `InitiateRiskBasedTwoFactorPhoneConfirmationMutation`
- `ConfirmRiskBasedTwoFactorPhoneConfirmationMutation`
- `SignUpNewMemberMutation`
- `AuthorizeBillingMutation`（或包内等价 authorize）

## 3. B 层落点

`Phase4` 成功后立即由本包的 `merchant_complete.py` 继续执行
OpenAI/pm-redirects/setup_intent/checkout-verify 纯 HTTP 链路；不存在只打 verify URL 的半链。

## 4. 输入 / 输出

输入：

- `ba_token`: `BA-...`
- `phone`: `+66XXXXXXXXX`
- 可选代理池

输出：

```json
{
  "status": "success|failed",
  "return_url": "https://...",
  "billing_agreement_id": "...",
  "ec_token": "EC-...",
  "stage": "Phase 4 ..."
}
```


## 5. A 完成后强制 B 层证据落盘

成功/结果对象会附带：

```json
{
  "b_layer": {
    "return_url": "...",
    "final_redirect_url": "...",
    "setup_intent": "seti_...",
    "setup_intent_client_secret": "seti_..._secret_...",
    "stripe_return_status": "succeeded|pending|failed|",
    "session_cookies": {},
    "protocol_mode": "http_only_full_protocol"
  }
}
```

Web job 目录：

- `runtime/jobs/{id}/b_layer_evidence.json`
- `runtime/jobs/{id}/merchant_replay_input.json`

禁止只留裸 `verification_url` 而不落 return_url/secret。
