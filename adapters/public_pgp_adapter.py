#!/usr/bin/env python3
"""PGP 公钥目录查询 (keys.openpgp.org VKS 公开 API)。

回答："这个邮箱/指纹背后有没有公开的 PGP 身份？密钥里绑定了哪些邮箱？"

## 数据价值

PGP 公钥服务器是完全公开的身份目录：
- keys.openpgp.org VKS v1 API：by-email / by-fingerprint，无需注册、无密钥
- 返回 OpenPGP 公钥块（含 fingerprint + 已验证邮箱 UIDs + 密钥创建时间）
- 公钥中的 UID 是持有人主动上传并经邮箱验证的公开自我声明

关联价值：
- 同一公钥绑定多个邮箱 → 同一人/同一组织的邮箱集合
- 密钥创建时间 → 身份活跃的时间锚点
- 与其他渠道邮箱交叉 → 强关联证据

## 访问模式

- `query(email)`：GET https://keys.openpgp.org/vks/v1/by-email/<urlencode(email)>
  - 200 → armored 公钥；404 → 该邮箱无已验证公钥；400 → 输入非法
- `query(fingerprint)`：GET https://keys.openpgp.org/vks/v1/by-fingerprint/<hex>
  - 指纹 40 字符（v4）或 64 字符（v6）十六进制

**判死的路径（实测 2026-10-21）**：keyserver.ubuntu.com 的 /pks/lookup
看似也公开，但其 robots.txt 对 `User-agent: *` 明确 `Disallow: /pks/`，
按本仓库红线直接停手，未建适配器，详见
docs/research/people-unconventional-p2-20261021.md。

## 合规

- 只读公开 API；不登录、不注册；桌面端 UA；5 秒请求间隔
- keys.openpgp.org 无 robots.txt（实测 404）→ 无 disallow
- data_boundary="fully_public"；EXPERIMENTAL，默认关闭
"""

from __future__ import annotations

import base64
import datetime
import re
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_FP_RE = re.compile(r"^[0-9a-fA-F]{40}$|^[0-9a-fA-F]{64}$")


class PgpKeyLookup(SafeResearchAdapter):
    """keys.openpgp.org VKS 公开公钥目录查询。"""

    source_domain = "keys.openpgp.org"
    source_type = "public_crypto_directory"
    data_boundary = "fully_public"
    requires_interaction = False
    min_request_interval = 5.0

    VKS_BASE = "https://keys.openpgp.org/vks/v1"

    # ------------------------------------------------------------------
    # SafeResearchAdapter 接口
    # ------------------------------------------------------------------

    def query(self, keyword: str, **params) -> dict[str, Any]:
        """入口：keyword 为邮箱或十六进制指纹。"""
        kw = (keyword or "").strip()
        if not _EMAIL_RE.match(kw) and not _FP_RE.match(kw.replace(" ", "")):
            return self._build_empty_result(kw, "invalid_input")
        return super().query(kw, **params)

    def _build_url(self, keyword: str, **params) -> str:
        clean = keyword.replace(" ", "")
        if _FP_RE.match(clean):
            return "{}/by-fingerprint/{}".format(self.VKS_BASE, clean.upper())
        return "{}/by-email/{}".format(
            self.VKS_BASE, urllib.parse.quote(keyword, safe="")
        )

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0 Safari/537.36",
            "Accept": "application/pgp-keys, text/plain, */*;q=0.1",
        }

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        if isinstance(raw_data, (bytes, bytearray)):
            text = bytes(raw_data).decode("ascii", errors="ignore")
        else:
            text = str(raw_data or "")
        if "BEGIN PGP PUBLIC KEY BLOCK" not in text:
            return {"found": False}
        return self.parse_key_block(text)

    # ------------------------------------------------------------------
    # 公钥块解析（纯公开结构，无需第三方库）
    # ------------------------------------------------------------------

    @staticmethod
    def parse_key_block(text: str) -> dict[str, Any]:
        """解析 armored 公钥块。

        返回 {found, fingerprint, emails, uids:[{name,email,comment}],
              key_created, key_id}。
        注：keys.openpgp.org 出于隐私设计，UID 中通常只保留已验证的
        邮箱（姓名为空），这是服务端行为，非解析缺失。
        """
        if "BEGIN PGP PUBLIC KEY BLOCK" not in text:
            return {"found": False}
        headers, raw = _parse_armor(text)
        emails: list[str] = []
        for c in headers.get("Comment", []):
            for m in re.finditer(
                r"<?([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})>?", c
            ):
                if m.group(1) not in emails:
                    emails.append(m.group(1))

        uids: list[dict[str, str]] = []
        key_created = ""
        key_id = ""
        for tag, body in _openpgp_packets(raw):
            if tag == 13:  # User ID
                uid = _parse_uid(body.decode("utf-8", errors="replace"))
                if uid not in uids:
                    uids.append(uid)
                    if uid["email"] and uid["email"] not in emails:
                        emails.append(uid["email"])
            elif tag == 6 and not key_created:  # Public-Key
                if len(body) >= 5 and body[0] in (4, 6):
                    ts = int.from_bytes(body[1:5], "big")
                    try:
                        key_created = datetime.datetime.fromtimestamp(
                            ts, datetime.timezone.utc
                        ).isoformat()
                    except (OverflowError, OSError, ValueError):
                        pass
        fingerprint = ""
        for c in headers.get("Comment", []):
            cands = re.sub(r"[^0-9A-Fa-f]", "", c)
            if len(cands) in (40, 64) and all(
                ch in "0123456789abcdefABCDEF" for ch in cands
            ):
                fingerprint = cands.upper()
                break
        if fingerprint:
            key_id = fingerprint[-16:]
        return {
            "found": True,
            "fingerprint": fingerprint,
            "key_id": key_id,
            "emails": emails,
            "uids": uids,
            "key_created": key_created,
            "source": "keys.openpgp.org",
        }


# ---------------------------------------------------------------------------
# 最小 OpenPGP 结构解析器（仅读 UID / Public-Key 包头，无密码学）
# ---------------------------------------------------------------------------


def _parse_armor(text: str) -> tuple[dict[str, list[str]], bytes]:
    headers: dict[str, list[str]] = {}
    body_lines: list[str] = []
    in_hdr, in_body = True, False
    for line in text.splitlines():
        if line.startswith("-----BEGIN"):
            in_hdr, in_body = True, False
            continue
        if line.startswith("-----END"):
            break
        if in_hdr:
            if line.strip() == "":
                in_hdr, in_body = False, True
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                headers.setdefault(k.strip(), []).append(v.strip())
        elif in_body:
            if line.startswith("="):  # CRC24 行
                continue
            body_lines.append(line.strip())
    return headers, base64.b64decode("".join(body_lines))


def _openpgp_packets(data: bytes):
    """生成 (tag, body)；仅支持定长包（VKS 返回的均为定长）。"""
    i = 0
    n = len(data)
    while i < n:
        ctb = data[i]
        i += 1
        if not ctb & 0x80:
            raise ValueError("invalid packet header")
        if ctb & 0x40:  # new format
            tag = ctb & 0x3F
            l1 = data[i]
            i += 1
            if l1 < 192:
                ln = l1
            elif l1 < 255:
                ln = ((l1 - 192) << 8) + data[i] + 192
                i += 1
            elif l1 == 255:
                ln = int.from_bytes(data[i : i + 4], "big")
                i += 4
            else:
                raise ValueError("partial body length not supported")
        else:  # old format
            tag = (ctb >> 2) & 0x0F
            lt = ctb & 0x03
            if lt == 0:
                ln = data[i]
                i += 1
            elif lt == 1:
                ln = int.from_bytes(data[i : i + 2], "big")
                i += 2
            elif lt == 2:
                ln = int.from_bytes(data[i : i + 4], "big")
                i += 4
            else:
                raise ValueError("indeterminate length not supported")
        yield tag, data[i : i + ln]
        i += ln


def _parse_uid(text: str) -> dict[str, str]:
    """解析 UID 字符串 'Name (comment) <email>'；缺失段留空。"""
    name, email, comment = "", "", ""
    m = re.search(r"<([^<>@\s]+@[^<>\s]+)>", text)
    rest = text
    if m:
        email = m.group(1).strip()
        rest = (text[: m.start()] + text[m.end() :]).strip()
    m2 = re.search(r"\(([^()]*)\)", rest)
    if m2:
        comment = m2.group(1).strip()
        rest = (rest[: m2.start()] + rest[m2.end() :]).strip()
    name = rest.strip()
    return {"name": name, "email": email, "comment": comment}
