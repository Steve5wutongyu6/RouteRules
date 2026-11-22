# RouteRules

Shadowrocket 配置:保留 johnshall 白名单分流,并把整个 `cloudflare.com` 家族固定走 PROXY。

## 为什么改

上游有一条 `DOMAIN-SUFFIX,cloudflare.com,Direct`。2026-11-22 在本机(同一份配置)实测,直连这条路不是"能用但慢":

| 域名 | 直连实测 | 走 PROXY 实测 |
| --- | --- | --- |
| `dash.cloudflare.com`(控制台) | 403 + `cf-mitigated: challenge`,挑战页只回状态行、正文 0 字节卡到超时 | 200,0.30s |
| `community.cloudflare.com` | 403 + `cf-mitigated: challenge`(3.6s) | — |
| `blog.cloudflare.com` | 200,4.4s | — |
| `www.cloudflare.com` | 200,1.33MB,3.0s | — |
| `cdnjs.cloudflare.com` | 200,1.0~1.9s | — |
| `api.cloudflare.com` / `challenges.cloudflare.com` | 改造前同样走直连 | 200,0.29~0.61s |

关键子域直接被挑战页拦下;而且控制台的 `cf_clearance` 绑定出口 IP —— 主站、API、Turnstile 组件不在同一个出口时,验证完刷新就失效。

补丁因此是一条家族级 pre-matching 规则:

```
DOMAIN-SUFFIX,cloudflare.com,PROXY,pre-matching
```

它先于上游的 `DOMAIN-SUFFIX,cloudflare.com,Direct` 命中(构建脚本会强制校验这个顺序),一次覆盖 dash / api / challenges / cdnjs / community 等所有子域,不用再逐个补。

## 用法

1. 导入 `sr_top500_whitelist.conf`,选中。
2. 设置 → 全局路由 → 配置。
3. 配置里的 `update-url` 已指向本仓库的 jsDelivr 地址,Shadowrocket 从这里更新。

规则测试:`bilibili.com` / `www.taobao.com` 为 DIRECT,`dash.cloudflare.com` / `api.cloudflare.com` / `challenges.cloudflare.com` 为 PROXY。

## 客户端排查(登录页能开、但按钮点不动 / 登录后白屏)

这几条都是"分流已经改了、浏览器还停在旧状态"造成的,按顺序做:

1. **完全退出浏览器再打开**。只刷新不够:已建立的连接不会重新匹配规则,指向旧直连出口的 socket 会被继续复用。
2. **清掉 `cloudflare.com` 的 Cookie 再登录**。改造前拿到的 `cf_clearance` / `__cf_bm` 绑定的是旧的国内出口 IP,换到代理出口后一律失效;此时页面能开,但 XHR / JS 会拿到 403 挑战页 → 白屏、按钮无反应。
3. **代理不要用"自动测速/负载均衡"策略组**。出口 IP 一变 `cf_clearance` 立刻作废;固定一个节点。
4. Safari 的"阻止跨站跟踪"会拦 Turnstile 的第三方 iframe;点不动时换 Chrome,或对该站放行跨站 Cookie。
5. 复现时看开发者工具 Network:若 `dash.cloudflare.com` 的 XHR / `.js` 返回 403 且响应体是挑战页(`cf-mitigated: challenge`),就是出口或 clearance 问题,回到第 1~3 条。

## 自动更新

`.github/workflows/update.yml` 每天两次拉取上游 `sr_top500_whitelist.conf`,运行 `scripts/build_config.py` 生成配置并校验,通过后提交。校验中国直连规则、`FINAL,PROXY`、补丁规则、补丁必须排在 `DOMAIN-SUFFIX,cloudflare.com,Direct` 之前、DNS 和 update-url,失败不提交。

jsDelivr 对 `@main` 有缓存,需要立即生效可把 `update-url` 换成 raw.githubusercontent.com 地址。

## 构建

```bash
curl -fsSL -o upstream.conf \\
  https://johnshall.github.io/Shadowrocket-ADBlock-Rules-Forever/sr_top500_whitelist.conf
python3 scripts/build_config.py upstream.conf sr_top500_whitelist.conf
```

脚本是幂等的:已经带补丁的配置再跑一次输出不变。

广告版:改 `update.yml` 的上游 URL,并同步修改 `build_config.py` 里的 `UPDATE_URL` 文件名。
