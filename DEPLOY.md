# 服务器部署说明（PP-TH-）

更新：2026-08-12  

目标：把本仓库 **Web 控制台** 部署到 VPS；用户自行填写 BA / 手机号 / **自己的代理**。  
**服务器不预置住宅代理池**（`PAYPAL_PROXY_ENABLED=0`，无共享 `PAYPAL_PROXY_URL`）。  
资料：**地址默认在线 OSM**；姓名/证件本地生成。Buyer：`legacy` | `elevate_bind`。

仓库：https://github.com/suixin00001111/PP-TH-

**交流**：部署 / 出网 / systemd 等问题可进 QQ 群 **`1098798456`** 一起沟通（提问请打码密钥与代理）。详见 [README.md](./README.md)。

---

## 1. 访问地址（部署成功后）

```text
http://<服务器公网IP>:8080/
```

健康检查：

```text
GET http://<IP>:8080/api/health  →  {"ok":true,...}
```

运行时枚举（应含买家模式与多引擎选项）：

```text
GET http://<IP>:8080/api/runtime
```

期望字段示例：

- `default.fingerprint_source=random`（服务器 `.env` 推荐纯协议）
- `fingerprint_sources` 含 `random` / `headless` / `roxy`（**可选**，不是仅 `["random"]`）
- `buyer_identity_modes` 含 `legacy` 与 `elevate_bind`

---

## 2. 一键安装 / 升级（推荐）

在 **服务器本机终端**（云厂商 Web Console / VNC / 已放行的 SSH）以 root 执行：

```bash
curl -fsSL https://raw.githubusercontent.com/suixin00001111/PP-TH-/main/deploy/install.sh -o /tmp/pp-th-install.sh
bash /tmp/pp-th-install.sh
```

或已有仓库目录时：

```bash
cd /opt/pp-th
git pull origin main
bash deploy/install.sh
```

脚本会：

1. 安装 `python3` / `git` / `curl`  
2. 克隆或更新到 `/opt/pp-th`  
3. 创建 venv 并 `pip install -r requirements.txt`  
4. 写入 **无代理密钥** 的 `.env`（**纯协议默认**：random / protocol / python_generated）  
5. 安装并启动 **systemd** 服务 `pp-th`：`0.0.0.0:8080`  
6. 尽量放行防火墙 8080  

> 默认不装 Playwright。用户若在页面选 Headless，需自行在服务器安装 headless 依赖，否则任务会报缺浏览器。生产多租户建议引导用户用 **纯协议** 或自备代理 + 纯协议。

服务管理：

```bash
systemctl status pp-th
systemctl restart pp-th
journalctl -u pp-th -f
```

---

## 3. 用户如何用（自己填代理）

1. 打开 `http://IP:8080/`  
2. 填写 **BA Token**、**手机号**（区号匹配国家）、选择 **国家**  
3. 选择 **Buyer 身份**：原版 / 升 Guest 绑 EC  
4. 风控三项：服务器推荐保持 **纯协议**（random / protocol / python_generated）；本机有 Chromium 才可选 Headless  
5. 需要代理：勾选启用，填 `host:port:user:pass` 或 `socks5h://...`（见 [PROXY.md](./PROXY.md)）  
6. **先点「测试代理」** 看到出口 IP，再「开始执行」  
7. 不填代理 = 服务器本机直连（仅调试；真 BA 建议目标国住宅代理）

---

## 4. 云防火墙 / 安全组（必做）

| 端口 | 用途 |
|------|------|
| **8080/tcp** | Web 控制台 |
| 22/tcp | SSH（建议仅管理 IP） |

仅开系统 `ufw` 不够时，还要在 **厂商安全组** 放行 8080。

---

## 5. 从本机无法 SSH 时

常见：`Error reading SSH protocol banner`、白名单、fail2ban。

处理：

1. 云控制台 **VNC / 网页终端**  
2. 放开你的公网 IP 或临时 `0.0.0.0/0`（用完改回）  
3. 网页终端执行第 2 节安装脚本  
4. 浏览器访问 `/api/health` 验证  

**不要把 root 密码长期放在 Git / 聊天记录；部署后改密 + 密钥登录。**

---

## 6. 已有旧版 8080 进程时

```bash
pkill -f 'python.*web.py' || true
systemctl restart pp-th
```

确认版本：

```bash
cd /opt/pp-th && git log -1 --oneline
curl -s http://127.0.0.1:8080/api/runtime
curl -s http://127.0.0.1:8080/api/health
```

新版特征：

- 有 `buyer_identity_modes`
- `fingerprint_sources` 为多值（含 headless/roxy），**不是**旧版「仅 random 锁定」
- UI 有 Buyer 模式下拉；**地址默认在线 OSM** 由服务端生成（失败回退本地池）；其它 PII 本地生成

---

## 7. 可选：Nginx 反代 + HTTPS

```nginx
server {
  listen 80;
  server_name your.domain;
  location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

证书可用 certbot。生产建议 `PAYPAL_WEB_COOKIE_SECURE=1`（仅 HTTPS）。

---

## 8. 环境变量（服务器侧）

| 变量 | 服务器建议 |
|------|------------|
| `PAYPAL_RUNTIME_MODE` | `protocol` |
| `PAYPAL_FINGERPRINT_SOURCE` | `random` |
| `PAYPAL_DATADOME_MODE` | `protocol` |
| `PAYPAL_MTR_RUNTIME` | `python_generated` |
| `PAYPAL_ONLINE_ADDRESS` | `1`（若机房出网差可改 `0`） |
| `PAYPAL_PROXY_ENABLED` | `0`（用户在 Web 填） |
| `PAYPAL_USE_SYSTEM_PROXY` | `0` |
| `PAYPAL_CONTINUE_MERCHANT` | `0` |
| `PAYPAL_WEB_PRODUCTION` | `1` |

**不要**在服务器 `.env` 写死共享住宅账号。

---

## 9. 排障

| 现象 | 处理 |
|------|------|
| 浏览器打不开 8080 | 安全组 / ufw；`systemctl status pp-th` |
| 仍是很旧的 UI | `git pull` + `bash deploy/install.sh`；清浏览器缓存 |
| 选了 Headless 报缺 playwright | 装 headless 依赖，或改回纯协议三项 |
| 任务代理失败 | 用户自测代理；见 [PROXY.md](./PROXY.md) |
| 升权相关报错 | 确认传了 `elevate_bind`；假/死 BA 只能测到 Phase2；Live 升权需新 BA + OTP |
| 想关在线地址 | 环境变量 `PAYPAL_ONLINE_ADDRESS=0` 后重启 web |

---

## 10. 安全提醒

- 部署用过的 root 密码请 **立即修改**  
- 限制 SSH 来源 IP  
- 仓库为私有研究用途；对外暴露时注意访问控制与日志脱敏（[SANITIZATION.md](./SANITIZATION.md)）

更细的 CentOS 7 / conda 历史笔记见 [HANDOFF.md](./HANDOFF.md) §7（手工部署路径，与 `install.sh` 可并存参考）。
