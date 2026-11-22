#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 johnshall 上游 Shadowrocket 配置构建本仓库使用的公开配置。

做的事：
  1. 删除 [MITM] 里可能存在的个人证书（ca-p12 / ca-passphrase），绝不把私钥提交到仓库；
  2. 在 [Rule] 最前面插入 Cloudflare 控制台(dash/api/人机验证)修复规则；
  3. 把 dns-server 改成「阿里 DoH + 两个 IP 兜底」，避免节点异常时 DNS 引导链断掉；
  4. 把 update-url 指向本仓库（jsDelivr），Shadowrocket 以后从本仓库自动更新；
  5. 对结果做安全检查：必须保留中国直连规则、FINAL,PROXY、补丁规则等，否则构建失败。

用法：
    python3 scripts/build_config.py upstream.conf sr_top500_whitelist.conf
"""
import argparse
import re
import sys

# Cloudflare 控制台真正要用的三个域名,必须走同一个出口(这里统一 PROXY):
#   dash.cloudflare.com        —— 控制台页面。直连会被 403 Managed Challenge 拦住,
#                                且挑战页 HTML 在国内直连路径上收不完(实测 0 bytes 超时)。
#   api.cloudflare.com         —— 控制台的 XHR 接口,与控制台同出口才不会被当成两个会话。
#   challenges.cloudflare.com  —— 人机验证组件(Turnstile)。
# 上游有 DOMAIN-SUFFIX,cloudflare.com,Direct,所以这三条必须 pre-matching 抢在前面。
PATCH_RULES = [
    "DOMAIN-SUFFIX,dash.cloudflare.com,PROXY,pre-matching",
    "DOMAIN-SUFFIX,api.cloudflare.com,PROXY,pre-matching",
    "DOMAIN-SUFFIX,challenges.cloudflare.com,PROXY,pre-matching",
]
UPSTREAM_DIRECT_RULE = re.compile(r"^DOMAIN-SUFFIX,cloudflare\.com,(Direct|DIRECT)\s*$", re.IGNORECASE | re.MULTILINE)
DNS_SERVER = "https://dns.alidns.com/dns-query, 223.5.5.5, 223.6.6.6"
UPDATE_URL = "https://cdn.jsdelivr.net/gh/Steve5wutongyu6/RouteRules@main/sr_top500_whitelist.conf"
MARK_BEGIN = "# === CF Dashboard/Challenge Fix (patch) ==="
MARK_END = "# === CF Dashboard/Challenge Fix end ==="
PATCH_COMMENT = (
    "# 让 Cloudflare 控制台、它的 API 和人机验证组件走同一出口(pre-matching 先于上游的\n"
    "# DOMAIN-SUFFIX,cloudflare.com,Direct),否则直连的挑战页打不开、cf_clearance 也会\n"
    "# 因为出口 IP 不一致而反复失效。\n"
)


def strip_secrets(lines):
    """删掉任何可能包含私钥的行（防御性，正常上游没有）。"""
    return [
        line
        for line in lines
        if not re.match(r"^\s*(ca-p12|ca-passphrase)\s*=", line, re.IGNORECASE)
    ]


def insert_patch_rules(lines):
    """把补丁规则插到 [Rule] 的第一行，保证 pre-matching 先于上游的 cloudflare.com,Direct。"""
    if any(MARK_BEGIN in line for line in lines):
        return lines
    existing = {line.strip() for line in lines}
    rules = [rule for rule in PATCH_RULES if rule not in existing]
    out, inserted = [], False
    for line in lines:
        out.append(line)
        if not inserted and re.match(r"^\s*\[Rule\]\s*$", line, re.IGNORECASE):
            out.append(MARK_BEGIN + "\n")
            out.append(PATCH_COMMENT)
            for rule in rules:
                out.append(rule + "\n")
            out.append(MARK_END + "\n")
            inserted = True
    if not inserted:
        raise ValueError("上游配置里找不到 [Rule] 段")
    return out


def replace_general(lines, key, value):
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=.*$", re.IGNORECASE)
    out, found = [], False
    for line in lines:
        if pattern.match(line):
            out.append(f"{key} = {value}\n")
            found = True
        else:
            out.append(line)
    if found:
        return out
    # 没有该键：插到 [General] 后面
    out, inserted = [], False
    for line in lines:
        out.append(line)
        if not inserted and re.match(r"^\s*\[General\]\s*$", line, re.IGNORECASE):
            out.append(f"{key} = {value}\n")
            inserted = True
    return out


def validate(text):
    problems = []
    if len(text) < 20000:
        problems.append("配置太小，可能上游返回了错误页")
    if "<html" in text.lower():
        problems.append("内容像 HTML 错误页")
    for needle in (
        "[General]",
        "[Rule]",
        "GEOIP,CN,DIRECT",
        "DOMAIN-SUFFIX,cn,DIRECT",
        "FINAL,PROXY",
        *PATCH_RULES,
        f"dns-server = {DNS_SERVER}",
        f"update-url = {UPDATE_URL}",
    ):
        if needle not in text:
            problems.append(f"缺少关键内容: {needle}")
    if re.search(r"^\s*ca-p12\s*=", text, re.IGNORECASE | re.MULTILINE):
        problems.append("仍然包含 ca-p12，拒绝提交")
    if re.search(r"^\s*ca-passphrase\s*=", text, re.IGNORECASE | re.MULTILINE):
        problems.append("仍然包含 ca-passphrase，拒绝提交")
    # 补丁规则必须排在上游的 cloudflare.com,Direct 之前,pre-matching 才能抢先命中。
    upstream_direct = UPSTREAM_DIRECT_RULE.search(text)
    patch_pos = [text.index(rule) for rule in PATCH_RULES if rule in text]
    if upstream_direct and patch_pos and min(patch_pos) > upstream_direct.start():
        problems.append("补丁规则必须排在 DOMAIN-SUFFIX,cloudflare.com,Direct 之前")
    rule_lines = [l for l in text.splitlines() if l and not l.startswith("#") and l.lstrip().startswith(("DOMAIN", "IP-CIDR", "GEOIP", "FINAL", "RULE-SET"))]
    if len(rule_lines) < 700:
        problems.append(f"规则数量异常: {len(rule_lines)}")
    if problems:
        raise ValueError("配置校验失败：\n  - " + "\n  - ".join(problems))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="上游原始 conf")
    ap.add_argument("output", help="输出的补丁版 conf")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    lines = strip_secrets(lines)
    lines = insert_patch_rules(lines)
    lines = replace_general(lines, "dns-server", DNS_SERVER)
    lines = replace_general(lines, "update-url", UPDATE_URL)

    text = "".join(lines)
    if not text.endswith("\n"):
        text += "\n"

    validate(text)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"built: {args.output} ({len(text)} bytes)")


if __name__ == "__main__":
    main()
