# 逆向笔记：pay.153 泰国全协议 → 本地源码包

## 前端证据（2026-07-19 抓取）

站点：`https://pay.153.ink/paypal-pay/`

- `static/app.js`：`API_BASE = '/paypal-pay/api'`
- 国家下拉含 `TH · 泰国 PayPal`
- 提交 payload：
  ```js
  { paypal_url, phone, country, proxies, agreement_only: false }
  ```
- 阶段进度映射：
  - Phase 0 协议页
  - Phase 1 风控/指纹
  - Phase 2 创建账号
  - Phase 3 短信验证/注册
  - Phase 4 最终授权
- 状态：`queued|running|awaiting_captcha|awaiting_otp|completed|failed|cancelled`

## 后端不可下载

`/paypal-pay/api/*` 只暴露 job 控制面，**没有**公开 Python 源码。
因此“泰国全协议源码”不能从站点直接 dump，只能：

1. 对照前端状态机 API；
2. 对照已公开的 **巴西纯 HTTP 全协议包**（同 Phase0-4）；
3. 用 `神奇的小PP` 中的拨号映射 `66→TH` 与多国 signup 经验，做 TH 资料/locale 切换。

## 本包策略

把巴西 `paypal-brazil-enhanced` 作为 A 层纯协议内核，区域参数换成 TH，
产出与巴西包同形态的可运行源码树（`main.py` + `web.py` + `paypal/*`）。
