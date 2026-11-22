# RouteRules

Shadowrocket 配置:保留 johnshall 白名单分流,并把 Cloudflare 控制台一族(dash / api / challenges)固定走 PROXY。

## 修复内容

上游有一条 `DOMAIN-SUFFIX,cloudflare.com,Direct`,会把控制台本身也送去直连。2026-11-22 在本机 Shadowrocket(同一份配置)实测:

| 域名 | 当前命中 | 实测结果 |
| --- | --- | --- |
| `dash.cloudflare.com` | Direct(被 `cloudflare.com` 那条命中) | `HTTP 403` + `cf-mitigated: challenge`,挑战页只回状态行、正文 0 字节卡到超时 → 浏览器一直转圈打不开 |
| `api.cloudflare.com` | Direct | 直连可通,但和控制台不在同一出口 |
| `challenges.cloudflare.com` | PROXY(旧补丁) | 200,出口 IP `38.47.124.239`(JP) |
| `www.cloudflare.com` | Direct | 200,正常返回 1.3 MB,出口 IP `58.243.163.128`(CN) —— 直连本身没问题 |

也就是说:控制台主站走 Direct(国内出口)、验证组件走 PROXY(日本节点),出口 IP 不一致,加上直连拿不到挑战页,于是控制台打不开、`cf_clearance` 也会反复失效。

补丁因此从一条扩成三条 `pre-matching` 规则,让控制台、它的接口和验证组件共用同一个出口:

```
DOMAIN-SUFFIX,dash.cloudflare.com,PROXY,pre-matching
DOMAIN-SUFFIX,api.cloudflare.com,PROXY,pre-matching
DOMAIN-SUFFIX,challenges.cloudflare.com,PROXY,pre-matching
```

`pre-matching` 保证这三条先于上游的 `DOMAIN-SUFFIX,cloudflare.com,Direct` 命中;上游其余规则一条没动。

## 用法

1. 导入 `sr_top500_whitelist.conf`,选中。
2. 设置 → 全局路由 → 配置。
3. 配置里的 `update-url` 已指向本仓库的 jsDelivr 地址,Shadowrocket 从这里更新。

验证:规则测试 `bilibili.com` / `www.taobao.com` 为 DIRECT,`dash.cloudflare.com` / `api.cloudflare.com` / `challenges.cloudflare.com` 为 PROXY;然后打开 <https://dash.cloudflare.com/>,应直接出登录页(不再 403 转圈)。

## 自动更新

`.github/workflows/update.yml` 每天两次拉取上游 `sr_top500_whitelist.conf`,运行 `scripts/build_config.py` 生成配置并校验,通过后提交。校验中国直连规则、`FINAL,PROXY`、三条补丁规则、补丁必须排在 `DOMAIN-SUFFIX,cloudflare.com,Direct` 之前、DNS 和 update-url,失败不提交。

jsDelivr 对 `@main` 有缓存,需要立即生效可把 `update-url` 换成 raw.githubusercontent.com 地址。

## 构建

```bash
curl -fsSL -o upstream.conf \
  https://johnshall.github.io/Shadowrocket-ADBlock-Rules-Forever/sr_top500_whitelist.conf
python3 scripts/build_config.py upstream.conf sr_top500_whitelist.conf
```

脚本是幂等的:已经带补丁的配置再跑一次输出不变。

广告版:改 `update.yml` 的上游 URL,并同步修改 `build_config.py` 里的 `UPDATE_URL` 文件名。
