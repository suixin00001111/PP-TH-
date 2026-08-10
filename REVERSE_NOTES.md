# 逆向笔记（历史对照，非现行实现规范）

> 更新说明：2026-08-10  
> 本文记录早期「对照 pay.153 / 巴西包做 TH 全协议本地化」的思路。  
> **现行产品已是 44 国多协议 + 升权 + 在线地址**；实现以源码与 [PROTOCOL_CHAIN.md](./PROTOCOL_CHAIN.md) / [README.md](./README.md) 为准，不要把本节当成 API 合同。

## 前端证据（历史抓取，约 2026-07）

站点示例：`https://pay.153.ink/paypal-pay/`（第三方 SaaS，**非本仓库依赖**）

- 控制面形态：`/paypal-pay/api/jobs` 一类 job API  
- 阶段语义对照：Phase0 协议页 → Phase1 风控 → Phase2 建号 → Phase3 OTP → Phase4 授权  
- 状态机语义：`queued|running|awaiting_captcha|awaiting_otp|completed|failed|…`

远端 **不提供** Python 源码下载，因此本地包只能：

1. 对照公开前端状态语义；  
2. 对照巴西等纯 HTTP 全协议实现（同 Phase0–4）；  
3. 自行多国化 locale / 区号 / 资料 / 证件。

## 本仓库演化（摘要）

| 阶段 | 内容 |
|------|------|
| 早期 | TH 参考状态机 + 巴西协议内核移植 |
| 中期 | 40+ 国 ProtocolContext、Web/CLI、代理、Headless/Roxy |
| 近期 | Web 风控可选；**elevate_bind**；OSM 在线地址；**44 国 ADDRESS_POOLS** |

## 现行入口（请用这些）

- 本地 API：`/api/jobs`、`/api/runtime`、`/api/regions`（见 README）  
- 升权：`buyer_identity_mode=elevate_bind`  
- 地址：`PAYPAL_ONLINE_ADDRESS` + `paypal/online_address.py`  
- 部署：`DEPLOY.md` + `deploy/install.sh`
