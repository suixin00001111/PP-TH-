# PP-TH 协议链路（多国纯 HTTP）

> 更新：2026-08-10  
> TH 仅为**状态机参考**；运行时按所选 `country` 绑定协议上下文。

## 0. 外部 SaaS 对照（非依赖）

`pay.153.ink` 等站点只提供远端 job API，**不是**本仓库源码来源。本包自包含：

```text
POST /api/jobs  { ba_token|paypal_url, phone, country, proxy*, buyer_identity_mode, risk knobs… }
  → Phase0..4 / awaiting_otp / failed|completed
```

## 1. 本包本地链路

```text
main.py / web.py
  → generate_user / card / address
       address: OSM online (PAYPAL_ONLINE_ADDRESS) → ADDRESS_POOLS[country] → Faker
  → PayPalFlow.run()
       或 IdentityElevationPayPalFlow.run()   # buyer_identity_mode=elevate_bind
      Phase0: GET /agreements/approve?ba_token=BA-...
              redirects, ssrt/cookies, DataDome 边缘处理, ModXO action ids
      Phase1: 指纹 / Tealeaf / analytics（巴西公开包对齐：在 Phase2 之前）
      Phase2: ModXO server-action → onboardingRedirect → EC token / signup URL
      Phase3: Griffin + 2FA 手机确认 + OTP + SignUpNewMember
              （country=选中国；仅 BR 可带 CPF）
      Phase4: AuthorizeBillingAgreement → return_url / BA id
              · legacy：Hagrid/review 绑定 buyer
              · elevate_bind：
                    _elevate_guest_identity
                 →  _bind_buyer_to_current_ec
                 →  authorize（可 skip_initial_hagrid）
```

### 1.1 买家身份模式

| mode | 入口 | 行为 |
|------|------|------|
| `legacy` | 默认 | Phase4 由 review/Hagrid 绑定 buyer |
| `elevate_bind` | Web / `--buyer-mode` / API | `paypal/elevation_flow.py`：严格 EC 门控 + Guest 升权 + 绑 EC 后再授权 |

别名（归一到 `elevate_bind`）：`identity_elevation`、`elevate`、`v2`、`guest_bind`、`bind_ec` 等。  
Web 升权任务类：`WebElevationPayPalFlow`（OTP 适配 + 升权）。

### 1.2 风控引擎（与链路正交）

| 维度 | 纯协议 | Headless | Roxy |
|------|--------|----------|------|
| 指纹 | `random` | Playwright | Local API |
| DataDome | `protocol` | Playwright | Local API |
| MTR | `python_generated` | Playwright | Local API |

服务器 `.env` 常默认纯协议；Web 表单可改选。不改变 Phase 顺序。

## 2. 关键 GraphQL / HTTP

`paypal/graphql.py`（多国共用，参数随 country/lang）：

- `CheckoutSessionDataQuery`
- `GriffinMetadataQuery`
- `InitiateRiskBasedTwoFactorPhoneConfirmationMutation`
- `ConfirmRiskBasedTwoFactorPhoneConfirmationMutation`
- `SignUpNewMemberMutation`
- `AuthorizeBillingMutation`（或包内等价 authorize）
- 升权相关：`BUYER_CONTEXT_QUERY`、`BUYER_FUNDING_CONTEXT_QUERY` 等

## 3. B 层落点（可选）

`PAYPAL_CONTINUE_MERCHANT=1` 时，A 成功后由 `merchant_complete.py` 继续商户 HTTP 链。  
**Web 默认关闭**，仅 A 层。

## 4. 输入 / 输出

输入：

- `ba_token`: `BA-...`（格式约 `^BA-[A-Za-z0-9]{8,80}$`）
- `phone`: 带国际区号，**必须匹配 country**
- `country`: 44 国之一
- `buyer_identity_mode`: `legacy` | `elevate_bind`
- 可选代理、风控三项、OTP

输出（示意）：

```json
{
  "status": "success|failed",
  "return_url": "https://...",
  "billing_agreement_id": "...",
  "ec_token": "EC-...",
  "stage": "Phase …",
  "buyer_identity_mode": "elevate_bind"
}
```

## 5. 冒烟预期（假 BA）

- 可到 Phase0 页面加载、Phase1 信标、Phase2 server-action  
- **预期**失败：无 EC、`authchallenge`、`generic-error`、`INVALID_TOKEN`  
- **不卡死**即引擎健康；全链路成功需真实 BA + 出口质量

## 6. 相关文档

- [README.md](./README.md) 总览  
- [SETUP.md](./SETUP.md) 安装  
- [PROXY.md](./PROXY.md) 出口  
- [HANDOFF.md](./HANDOFF.md) / [AI_HANDOFF.md](./AI_HANDOFF.md) 交接  
