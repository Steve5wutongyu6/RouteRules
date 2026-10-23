#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 johnshall 上游 Shadowrocket 配置构建本仓库使用的公开配置。

做的事：
  1. 删除 [MITM] 里可能存在的个人证书（ca-p12 / ca-passphrase），绝不把私钥提交到仓库；
  2. 在 [Rule] 最前面插入 Cloudflare 人机验证修复规则；
  3. 把 dns-server 改成「阿里 DoH + 两个 IP 兜底」，避免节点异常时 DNS 引导链断掉；
  4. 把 update-url 指向本仓库（jsDelivr），Shadowrocket 以后从本仓库自动更新；
  5. 对结果做安全检查：必须保留中国直连规则、FINAL,PROXY、补丁规则等，否则构建失败。

用法：
    python3 scripts/build_config.py upstream.conf sr_top500_whitelist.conf
"""
import argparse
import re
import sys

PATCH_RULE = "DOMAIN-SUFFIX,challenges.cloudflare.com,PROXY,pre-matching"
DNS_SERVER = "https://dns.alidns.com/dns-query, 223.5.5.5, 223.6.6.6"
UPDATE_URL = "https://cdn.jsdelivr.net/gh/Steve5wutongyu6/RouteRules@main/sr_top500_whitelist.conf"
MARK_BEGIN = "# === CF Challenge Fix (patch) ==="
MARK_END = "# === CF Challenge Fix end ==="


def strip_secrets(lines):
    """删掉任何可能包含私钥的行（防御性，正常上游没有）。"""
    return [
        line
        for line in lines
        if not re.match(r"^\s*(ca-p12|ca-passphrase)\s*=", line, re.IGNORECASE)
    ]


def insert_patch_rule(lines):
    if any(MARK_BEGIN in line for line in lines):
        return lines
    out, inserted = [], False
    for line in lines:
        out.append(line)
        if not inserted and re.match(r"^\s*\[Rule\]\s*$", line, re.IGNORECASE):
            out.append(MARK_BEGIN + "\n")
            out.append("# 让 Cloudflare 验证组件与主站走同一出口；pre-matching 保证先于 cloudflare.com,Direct 命中\n")
            out.append(PATCH_RULE + "\n")
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
        PATCH_RULE,
        f"dns-server = {DNS_SERVER}",
        f"update-url = {UPDATE_URL}",
    ):
        if needle not in text:
            problems.append(f"缺少关键内容: {needle}")
    if re.search(r"^\s*ca-p12\s*=", text, re.IGNORECASE | re.MULTILINE):
        problems.append("仍然包含 ca-p12，拒绝提交")
    if re.search(r"^\s*ca-passphrase\s*=", text, re.IGNORECASE | re.MULTILINE):
        problems.append("仍然包含 ca-passphrase，拒绝提交")
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
    lines = insert_patch_rule(lines)
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
