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

# Cloudflare 全家族统一走 PROXY。上游有 DOMAIN-SUFFIX,cloudflare.com,Direct,而实测
# 直连这条路:控制台 dash.cloudflare.com 只回 403 挑战页(挑战页正文在国内直连路径上
# 收不完,0 bytes 卡到超时),社区 community.cloudflare.com 同样是 403
# cf-mitigated: challenge,首页/文档/blog 慢到 2~5s;走 PROXY 后 dash / api /
# challenges / insights 都是 0.3~0.6s 返回。而且控制台的 cf_clearance 绑定出口 IP,
# 主站、接口、人机验证组件必须同一个出口。pre-matching 保证先于上游那条 Direct 命中。
PATCH_RULES = [
    "DOMAIN-SUFFIX,cloudflare.com,PROXY,pre-matching",
]
UPSTREAM_DIRECT_RULE = re.compile(r"^DOMAIN-SUFFIX,cloudflare\.com,(Direct|DIRECT)\s*$", re.IGNORECASE | re.MULTILINE)
DNS_SERVER = "https://dns.alidns.com/dns-query, 223.5.5.5, 223.6.6.6"
UPDATE_URL = "https://cdn.jsdelivr.net/gh/Steve5wutongyu6/RouteRules@main/sr_top500_whitelist.conf"
MARK_BEGIN = "# === CF Dashboard/Challenge Fix (patch) ==="
MARK_END = "# === CF Dashboard/Challenge Fix end ==="
PATCH_COMMENT = (
    "# 让整个 cloudflare.com 家族走 PROXY(pre-matching 先于上游的\n"
    "# DOMAIN-SUFFIX,cloudflare.com,Direct)。直连的控制台/社区子域只回 403 挑战页,\n"
    "# 首页等要 2~5s;控制台的 cf_clearance 也要求主站与验证组件同一个出口。\n"
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
