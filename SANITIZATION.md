# Sanitization（脱敏与仓库卫生）

更新：2026-08-10

## 禁止提交

- 真实 BA token、OTP、cookie、HAR、抓包全文  
- 代理账号密码、住宅池、Roxy / SMSBower API Key  
- 生产 `.env`、服务器 root 密码、私钥  
- 真实用户 PII（姓名手机邮箱若来自线上任务）

## 仓库允许

- `.env.example` 中的**无密钥**默认项（含 `PAYPAL_ONLINE_ADDRESS=1` 等开关）  
- Faker / 本地 `ADDRESS_POOLS` 合成地址与随机测试卡 BIN 规则  
- 假 BA 格式样例（如 `BA-TEST…`）仅用于文档与单测

## 运行时

- 日志默认脱敏 token / 手机 / 卡号 / 邮箱（见 `sanitize_for_log` 等）  
- Web 任务内存态；重启即丢；按 `paypal_web_device_id` 隔离  
- 代理与密钥：Web 表单或环境变量注入，**不要**写进 git

## 文档

- [DEPLOY.md](./DEPLOY.md) / [HANDOFF.md](./HANDOFF.md) 中的服务器 IP 等为运维参考；**密码永不入库**  
- 对外分享日志前先检查是否含 proxy URL 明文
