# 服务器部署说明（PP-TH-）

更新：2026-08-10  

目标：把本仓库的 **Web 控制台** 部署到 VPS，对外可自行填写 BA / 手机号 / **自己的代理**。  
**服务器不预置住宅代理池**（`PAYPAL_PROXY_ENABLED=0`，无共享 `PAYPAL_PROXY_URL`）。

仓库：https://github.com/suixin00001111/PP-TH-

---

## 1. 访问地址（部署成功后）

```text
http://<服务器公网IP>:8080/
```

示例（若 IP 为 `156.238.252.168`）：

```text
http://156.238.252.168:8080/
```

健康检查：

```text
GET http://<IP>:8080/api/health  →  {"ok":true,...}
```

---

## 2. 一键安装 / 升级（推荐）

在 **服务器本机终端**（云厂商 Web Console / VNC / 已放行的 SSH）以 root 执行：

```bash
curl -fsSL https://raw.githubusercontent.com/suixin00001111/PP-TH-/main/deploy/install.sh -o /tmp/pp-th-install.sh
bash /tmp/pp-th-install.sh
```

或已有仓库目录时：

```bash
cd /opt/pp-th   # 或你的目录
git pull origin main
bash deploy/install.sh
```

脚本会：

1. 安装 `python3` / `git` / `curl`  
2. 克隆或更新到 `/opt/pp-th`  
3. 创建 venv 并 `pip install -r requirements.txt`  
4. 写入 **无代理密钥** 的 `.env`（纯协议默认）  
5. 安装并启动 **systemd** 服务 `pp-th`：`0.0.0.0:8080`  
6. 尽量放行防火墙 8080  

服务管理：

```bash
systemctl status pp-th
systemctl restart pp-th
journalctl -u pp-th -f
```

---

## 3. 用户如何用（自己填代理）

1. 打开 `http://IP:8080/`  
2. 填写 **BA Token**、**手机号**、选择 **国家**  
3. 需要代理时：勾选「启用代理」，填写自己的  
   `host:port:user:pass` / `socks5h://...` 等（见 [PROXY.md](./PROXY.md)）  
4. **先点「测试代理」** 看到出口 IP，再「开始执行」  
5. 不填代理 = 服务器本机直连（仅适合调试；真 BA 建议用户自备目标国住宅代理）

Web 风控三项固定巴西纯协议：`random` / `protocol` / `python_generated`（不弹浏览器）。

---

## 4. 云防火墙 / 安全组（必做）

在云面板放行：

| 端口 | 用途 |
|------|------|
| **8080/tcp** | Web 控制台（对外） |
| 22/tcp | SSH（建议仅管理 IP 白名单） |

仅开系统 `ufw` 不够时，还要在 **厂商安全组** 放行 8080。

---

## 5. 从本机无法 SSH 时

若出现：

- `Error reading SSH protocol banner`
- 22 端口能 connect 但无 `SSH-2.0` banner  
- 密码正确仍被断开  

常见原因：

1. **SSH 仅允许白名单 IP**（当前办公网 IP 未加白）  
2. 厂商「安全组」未放行 22，或只对特定来源开放  
3. `sshd` 异常 / fail2ban 封禁  

处理：

1. 登录云控制台 **VNC / 网页终端**（不依赖 22）  
2. 把你的公网 IP 加入 SSH 白名单，或临时 `0.0.0.0/0`（用完改回）  
3. 在网页终端执行第 2 节安装脚本  
4. 浏览器访问 `http://IP:8080/api/health` 验证  

**不要把 root 密码提交到 Git / 聊天记录长期保存；部署后建议改密 + 密钥登录。**

---

## 6. 已有旧版 8080 进程时

`install.sh` 会尝试结束占用 8080 的旧 `web.py` 并改由 systemd 管理。  
若手工启动过：

```bash
pkill -f 'python.*web.py' || true
systemctl restart pp-th
```

确认版本（应含纯协议固定与最新文档提交）：

```bash
cd /opt/pp-th && git log -1 --oneline
curl -s http://127.0.0.1:8080/api/runtime | head
```

期望 `default.fingerprint_source=random`，且 `fingerprint_sources` 仅 `["random"]`（新版 Web 锁定）。

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
| `PAYPAL_PROXY_ENABLED` | `0`（用户在 Web 填） |
| `PAYPAL_USE_SYSTEM_PROXY` | `0` |
| `PAYPAL_CONTINUE_MERCHANT` | `0` |
| `PAYPAL_WEB_PRODUCTION` | `1` |

**不要**在服务器 `.env` 写死共享住宅账号；多租户各自在页面填写。

---

## 9. 排障

| 现象 | 处理 |
|------|------|
| 浏览器打不开 8080 | 安全组 / ufw 放行；`systemctl status pp-th` |
| 页面是旧 UI（仍有 Headless 下拉） | `bash /opt/pp-th/deploy/install.sh` 升级 |
| 任务代理失败 | 用户自测代理；见 [PROXY.md](./PROXY.md) |
| curl 77 on server | 少见；`ssl_env` 仍会镜像 CA |

---

## 10. 安全提醒

- 部署用过的 root 密码请 **立即修改**  
- 限制 SSH 来源 IP  
- 仓库为私有研究用途；对外暴露时注意访问控制与日志脱敏（[SANITIZATION.md](./SANITIZATION.md)）
