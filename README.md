# RouteRules

Shadowrocket 配置：保留 johnshall 白名单分流，并修复 Cloudflare 人机验证（`challenges.cloudflare.com` 走 PROXY）。

## 用法

1. 导入 `sr_top500_whitelist.conf`，选中。
2. 设置 → 全局路由 → 配置。
3. 配置里的 `update-url` 已指向本仓库的 jsDelivr 地址，Shadowrocket 从这里更新。

验证：规则测试 `bilibili.com` 为 DIRECT，`challenges.cloudflare.com` 为 PROXY。

## 自动更新

`.github/workflows/update.yml` 每天两次拉取上游 `sr_top500_whitelist.conf`，运行 `scripts/build_config.py` 生成配置并校验，通过后提交。校验中国直连规则、`FINAL,PROXY`、补丁规则、DNS 和 update-url，失败不提交。

jsDelivr 对 `@main` 有缓存，需要立即生效可把 `update-url` 换成 raw.githubusercontent.com 地址。

## 构建

```bash
curl -fsSL -o upstream.conf \
  https://johnshall.github.io/Shadowrocket-ADBlock-Rules-Forever/sr_top500_whitelist.conf
python3 scripts/build_config.py upstream.conf sr_top500_whitelist.conf
```

广告版：改 `update.yml` 的上游 URL，并同步修改 `build_config.py` 里的 `UPDATE_URL` 文件名。


