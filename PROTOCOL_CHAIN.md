# 泰国 PayPal 全协议链路（本地纯 HTTP）

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

## 1. 本包本地链路（对齐巴西全协议实现）

```text
main.py / web.py
  → generate_user/card/address
       address: OSM online (optional) → ADDRESS_POOLS[country] → Faker
  → PayPalFlow.run()  或  IdentityElevationPayPalFlow.run()  (buyer_identity_mode)
      Phase0: GET /agreements/approve?ba_token=BA-...
              follow redirects, extract ssrt / cookies / DataDome 判定
      Phase1: FraudNet fn_sync + Tealeaf + analytics (tz 按所选国)
      Phase2: ModXO Server Action create-account → EC token / signup URL
      Phase3: GriffinMetadata(country/lang)
              InitiateRiskBasedTwoFactorPhoneConfirmation (+cc)
              ConfirmRiskBasedTwoFactorPhoneConfirmation (OTP)
              SignUpNewMemberMutation (country=选中国, BR 可带 CPF)
      Phase4: AuthorizeBillingAgreement → return_url / BA id
              · legacy：Hagrid 上下文绑定 buyer
              · elevate_bind：_elevate_guest_identity → _bind_buyer_to_current_ec
                → authorize（可 skip_initial_hagrid）
```

### 1.1 买家身份模式

| mode | 入口 | 行为 |
|------|------|------|
| `legacy` | 默认 | Phase4 由 review/Hagrid 绑定 buyer |
| `elevate_bind`（别名 `identity_elevation` 等） | Web 下拉 / `--buyer-mode` / API | `paypal/elevation_flow.py`：严格 EC 门控 + Guest 升权 + 绑 EC 后再授权 |

Web 选择 `elevate_bind` 时使用 `WebElevationPayPalFlow`（OTP 适配 + 升权）。

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
