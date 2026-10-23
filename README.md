# RouteRules

给 Shadowrocket 用的「分流正确的 Cloudflare 人机验证修复」配置，并自带定时更新。

## 这个仓库解决什么

Cloudflare 的验证组件在 `challenges.cloudflare.com`，论坛主站在论坛域名。
原来的白名单配置里有一条：

```
DOMAIN-SUFFIX,cloudflare.com,Direct
```

它会连 `challenges.cloudflare.com` 也一起送去直连，而论坛主站走 `FINAL,PROXY`。
一次验证被拆成两条不同出口 IP 的连接，`cf_clearance`（绑定 IP + User-Agent）永远对不上，
于是验证完刷新又弹验证，或者一直“正在验证您是否是真人”。

本仓库在 `[Rule]` 最前面加一条前置规则：

```
DOMAIN-SUFFIX,challenges.cloudflare.com,PROXY,pre-matching
```

让验证组件和主站走同一个代理出口。**原配置的规则一条不动**（包括中国直连、GEOIP,CN,DIRECT、
top500 直连列表、FINAL,PROXY），所以 B 站、淘宝这些国内站点仍然直连。

## 文件

| 文件 | 说明 |
|---|---|
| `sr_top500_whitelist.conf` | 构建产物，Shadowrocket 直接导入这个 |
| `scripts/build_config.py` | 从上游配置生成本文件（加规则、改 DNS、写 update-url、做安全校验） |
| `.github/workflows/update.yml` | 每天两次拉上游并重新构建、提交 |

构建时会校验：必须包含 `GEOIP,CN,DIRECT`、`DOMAIN-SUFFIX,cn,DIRECT`、`FINAL,PROXY`、
补丁规则、正确 DNS 和 update-url；否则直接失败、不提交，避免把坏配置发出去。

> 首次使用时，请在仓库 **Settings → Actions → General → Workflow permissions** 里选择
> **Read and write permissions**，否则 Action 没有权限把更新 push 回仓库。

## 在 Shadowrocket 里使用

1. 把 `sr_top500_whitelist.conf` 导入 Shadowrocket（配置 → 添加配置 / 导入文件）。
2. 选中它（配置列表里勾选）。
3. 它已经内置了 `update-url`，指向本仓库的 jsDelivr 地址：
   `https://cdn.jsdelivr.net/gh/Steve5wutongyu6/RouteRules@main/sr_top500_whitelist.conf`
   以后 Shadowrocket 更新配置就是从这个地址拉。
4. 把旧的配置取消勾选/删除，避免选错。
5. 检查 **设置 → 全局路由** 为「配置」。

### 验证分流

Shadowrocket 规则测试：

- `challenges.cloudflare.com` → **PROXY**
- `bilibili.com` / `www.baidu.com` / `www.taobao.com` → **DIRECT**
- 打开 B 站、淘宝，日志里应为 DIRECT

## 自动更新是怎么跑的

```
GitHub Actions（每天 03:17 / 15:17 UTC）
  → 拉 johnshall 上游 sr_top500_whitelist.conf
  → python3 scripts/build_config.py upstream.conf sr_top500_whitelist.conf
  → 校验通过才 commit / push
  → Shadowrocket 从 jsDelivr 拉这个文件
```

上游更新后，国内直连列表、代理列表会跟着更新，而补丁规则和 DNS 兜底始终保留。

**注意**：jsDelivr 对 `@main` 有缓存（最长约 12 小时）。想立刻拿到最新文件，可以在
Shadowrocket 里把 `update-url` 临时改成：
`https://raw.githubusercontent.com/Steve5wutongyu6/RouteRules/main/sr_top500_whitelist.conf`
（需要能访问 raw.githubusercontent.com）。日常用 jsDelivr 即可。

## 安全说明

- 本仓库必须是 **public**，jsDelivr / Shadowrocket 才能直接拉取。
- 构建脚本会删除任何 `ca-p12` / `ca-passphrase`（MITM 证书私钥），不会把私钥提交上来。
- DNS 使用公共阿里 DoH + `223.5.5.5` / `223.6.6.6` 兜底，不含个人 HTTPDNS 账号地址。
- 仓库里没有节点、订阅、密码等任何代理凭据。
- 如果要给自己加 MITM 或私有 DNS，请在设备本地另行处理（但下次配置更新会覆盖，需自行权衡）。

## 手动构建 / 换广告版

```bash
curl -fsSL -o upstream.conf \
  https://johnshall.github.io/Shadowrocket-ADBlock-Rules-Forever/sr_top500_whitelist.conf
python3 scripts/build_config.py upstream.conf sr_top500_whitelist.conf
```

要换成广告过滤版：把 `update.yml` 里的上游 URL 改成 `sr_top500_whitelist_ad.conf`，
并把 `scripts/build_config.py` 的 `UPDATE_URL` 换成对应的文件名即可（脚本对两种格式都适用）。

## 为什么不用 Shadowrocket 模块

模块里的 `[Rule]` 是**整套覆盖**当前配置的规则表，不是追加。模块里只写一条规则时，
原配置的中国直连规则会全部失效，国内流量会落到默认 PROXY。这个仓库改的是配置本身，所以不会出这个问题。

## 回滚

- Shadowrocket 里取消勾选本配置，重新启用你原来的配置即可。
- 或把配置里的 `update-url` 改回上游地址，再点“更新配置”。
