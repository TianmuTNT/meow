# MEOW — Minecraft Encapsulation Over WebSocket

把 **Minecraft** 专有 TCP 流量 **封装** 为 **WebSocket**，在出口再 **解封装** 为原生 MC 流量，从而可经由 **Cloudflare Web CDN** 转发。

> **有趣的事实：MEOW 也可被称为 MEOW Encapsulation Over WebSocket**  
> 核心思路：MC ↔ WS 隧道 ↔ MC（中间段走 Cloudflare）

---

## 特性

- 入口监听原生 **TCP**，客户端无需改动
- 中间段走 **Cloudflare WSS**（可优选）
- 出口解封装直连你的 **Minecraft 实例** 或 **ZBProxy**
- 仅依赖 `websockets` + `python-dotenv`，轻量易部署
- 可通过 `.env` 配置

---

## 架构概览

```
[Minecraft Client] --TCP-->
[entry] --WSS-->
[Cloudflare] --WS-->
[exit] --TCP-->
[ZBProxy] --TCP-->
[Minecraft Server]
````

---

## 环境要求

- Python 3.9+
- 落地机上按指南安装并配置 **ZBProxy**  
  👉 参考项目：`https://github.com/layou233/ZBProxy`
- 一个可由 Cloudflare 托管的域名

---

## 安装依赖

在入口与出口机器上分别执行：

```bash
pip install -r requirements.txt
````

---

## 部署步骤
### 1) 落地机：部署 ZBProxy

* 按照 ZBProxy 官方仓库的安装与配置文档进行部署：

  * 仓库：`https://github.com/layou233/ZBProxy`
  * 目标：在 **127.0.0.1:25565**（或自定义端口）提供 Minecraft 的代理/转发能力

### 2) 落地机：部署 `exit`

1. 复制 `exit/.env.example` 为 `exit/.env` 并修改**必要参数**：

   * `WS_LISTEN_PORT`：任意指定，默认 `8765`
   * `MC_TARGET_HOST` / `MC_TARGET_PORT`：指向你的 ZBProxy/真实 MC 服（例如 `127.0.0.1:25565`）
   * `AUTH_TOKEN`：改为强口令，并与入口端保持一致

2. 启动 `exit`：

   ```bash
   python exit.py
   ```

   日志出现 `exit proxy listening on ws://0.0.0.0:8765` 即为正常。

### 3) Cloudflare 设置

1. **DNS**

   * 新建 `A` 或 `AAAA` 记录，将你的域名（如 `hyp.example.com`）指向落地机 IP
   * 勾选 **代理**（小橙云 = ON）

2. **SSL/TLS 模式**

   * `SSL/TLS -> Overview -> Flexible`
   * `Network -> WebSockets` 确保 **ON**

3. **规则：把请求转到出口端口**

   * 在 **Rules / Origin Rules**（或等价功能）中新建规则，匹配你的域名（如 `hyp.example.com`），设置：

     * **Override Origin Port = `WS_LISTEN_PORT`**（例如 8765）
   * 这样，客户端始终访问 `wss://hyp.example.com/tunnel`（默认 443），Cloudflare 回源到你在落地机 `exit` 监听的 **8765**。

> 说明：如你不会设置规则，可以把 `WS_LISTEN_PORT` 改为 **80**，同样满足 Flexible 到源站的明文回源。

### 4) 入口机：部署 `entry`

1. 复制 `entry/.env.example` 为 `entry/.env`，修改：

   * `WS_URL=wss://hyp.example.com/tunnel`
   * `AUTH_TOKEN` 与出口一致
   * （可选）`FORCE_HOST`/`FORCE_IP` 做 **Cloudflare优选**

2. 启动 `entry`：

   ```bash
   python entry.py
   ```

   日志出现 `entry proxy listening on ...` 与 `DNS pin: ...` 即为正常。

### 5) 客户端连接

* 打开 Minecraft 客户端，服务器地址填：

  ```
  <入口机IP>:<LISTEN_PORT>
  # 例如 127.0.0.1:25565
  ```
* 连接后：Client → entry(25565) → WSS → Cloudflare → WS → exit(8765) → TCP → ZBProxy/MC

---

## 调优建议

* `CHUNK`：建议 `16384`（≈单个 TLS record），常能减少抖动；必要时测试 `32768`。
* 心跳：`PING_INTERVAL=30~60`、`PING_TIMEOUT=20~25`，避免过于频繁的心跳插队。
* 优选：使用对目前线路最有益的 Cloudflare IP，例如落地机在美国，入口机在中国香港，则可以选用美国或香港 IP，千万不可以绕路。
* 安全：务必使用 **强 `AUTH_TOKEN`**，并限制出入口机的防火墙策略。

---

## 常见问题

* **Cloudflare 不回源到我自定义端口怎么办？**
  使用 **Origin Rules** 将回源端口覆盖为 `WS_LISTEN_PORT`（如 8765）。如不可用，可考虑把 `WS_LISTEN_PORT` 直接设为 80。

* **连接卡顿**
  适当增大 `CHUNK`、放宽 `PING_INTERVAL`，并确认 Cloudflare 侧没有对 `/tunnel` 做重写/缓存/挑战类规则。

---

## 许可证

本项目采用 [**Apache-2.0**](./LICENSE) 许可协议。
