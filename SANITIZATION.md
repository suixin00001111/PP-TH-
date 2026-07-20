# Sanitization

- 不包含真实 BA、手机、代理账号、cookie、HAR。
- 资料生成使用开源 Faker locale + 本地随机卡号；无远端 profile API。
- 日志默认脱敏 token / 手机 / 卡号 / 邮箱。
- config.py 仓库版本不提交代理密钥；运行时用 Web 填写或环境变量。
