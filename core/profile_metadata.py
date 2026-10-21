"""Maigret 式 profile 元数据解析 — 用户名深挖的第二跳。

存在性枚举只是入口：一个站点"有这个用户名"之后，profile 页里的
bio/昵称/公司/位置/公开链接才是真正的深挖材料（社工学：顺痕迹找根）。

设计原则：
- 纯函数，离线可测：输入 HTML/JSON 文本 + URL，输出结构化元数据。
- 本模块不联网、不登录；只抓公开 profile 页（抓取层在 adapter，
  受 robots + 限速 + 失败降级约束）。
- 通用 fallback 永远可用；专用解析按站点命中，命中则并补。
- 所有输出都是 lead：engine 侧转实体时只用已有实体类型词汇，
  并携带来源站点标注。

输出结构：
    {"site": str, "url": str, "display_name": str|None, "bio": str|None,
     "company": str|None, "location": str|None, "parser": str}
"""

from __future__ import annotations

import html as _html_mod
import re
from typing import Any, Callable
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# 通用 HTML 提取
# ---------------------------------------------------------------------------

_META_RE = re.compile(
    r'<meta\s+[^>]*?(?:property|name)=["\']([^"\']+)["\'][^>]*?'
    r'content=["\']([^"\']*)["\']',
    re.IGNORECASE | re.DOTALL,
)
_META_REV_RE = re.compile(
    r'<meta\s+[^>]*?content=["\']([^"\']*)["\'][^>]*?'
    r'(?:property|name)=["\']([^"\']+)["\']',
    re.IGNORECASE | re.DOTALL,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")

# 嵌入 JSON 中的 "key":"value"（GitHub/知乎等把 profile 数据塞在页面 JSON 里）
# value 允许 \" 转义
_EMBED_JSON_RE = re.compile(
    r'"(?P<key>[A-Za-z_][A-Za-z0-9_]*)"\s*:\s*"(?P<val>(?:[^"\\]|\\.)*)"'
)


def _as_text(html: Any) -> str:
    if html is None:
        return ""
    if isinstance(html, bytes):
        return html.decode("utf-8", errors="replace")
    return str(html)


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    t = _html_mod.unescape(_TAG_RE.sub(" ", _SCRIPT_STYLE_RE.sub(" ", text)))
    t = re.sub(r"\s+", " ", t).strip()
    return t or None


_UNICODE_ESC_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


def _unescape_json_str(s: str) -> str:
    """只解码 JSON 转义序列，不动已是 UTF-8 的中文字符。

    （旧实现误用 unicode_escape 把已解码的中文搅成 mojibake。）
    """
    if "\\" not in s:
        return s
    out = s.replace("\\\\", "\x00")
    out = out.replace('\\"', '"').replace("\\/", "/")
    out = _UNICODE_ESC_RE.sub(lambda m: chr(int(m.group(1), 16)), out)
    out = out.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")
    return out.replace("\x00", "\\")


def _meta_content(text: str, *names: str) -> str | None:
    """取第一个命中的 meta property/name 的 content。"""
    metas: dict[str, str] = {}
    for m in _META_RE.finditer(text):
        metas[m.group(1).strip().lower()] = m.group(2)
    for m in _META_REV_RE.finditer(text):
        metas[m.group(2).strip().lower()] = m.group(1)
    for n in names:
        v = metas.get(n.lower())
        if v:
            return v.strip()
    return None


def _title(text: str) -> str | None:
    m = _TITLE_RE.search(text)
    return _clean(m.group(1)) if m else None


def _embedded_json(text: str, keys: tuple[str, ...]) -> dict[str, str]:
    """从页面嵌入 JSON 中按 key 取值（第一个命中为准）。"""
    out: dict[str, str] = {}
    wanted = {k.lower() for k in keys}
    for m in _EMBED_JSON_RE.finditer(text):
        k = m.group("key").lower()
        if k in wanted and k not in out:
            out[k] = _unescape_json_str(m.group("val")).strip()
    return out


# ---------------------------------------------------------------------------
# 专用解析器
# ---------------------------------------------------------------------------

def _parse_generic(text: str) -> dict[str, str | None]:
    """通用 fallback：og:title / og:description / meta description / <title>。"""
    title = _clean(_meta_content(text, "og:title")) or _title(text)
    bio = _clean(_meta_content(text, "og:description", "description"))
    return {"display_name": title, "bio": bio, "company": None, "location": None}


def _parse_github(text: str) -> dict[str, str | None]:
    """GitHub profile：标题 'Name (login) · GitHub' + 嵌入 JSON bio/company/location。"""
    emb = _embedded_json(text, ("bio", "company", "location", "name"))
    title = _title(text)
    display_name = emb.get("name")
    if not display_name and title:
        # "张三 (zhangsan) · GitHub" / "zhangsan · GitHub"
        m = re.match(r"^(.*?)\s*[·•|]\s*GitHub", title)
        if m:
            inner = m.group(1).strip()
            pm = re.match(r"^(.+?)\s*\(([^)]+)\)$", inner)
            display_name = pm.group(1).strip() if pm else inner
    return {
        "display_name": display_name,
        "bio": emb.get("bio") or _clean(_meta_content(text, "og:description")),
        "company": emb.get("company"),
        "location": emb.get("location"),
    }


def _parse_gitee(text: str) -> dict[str, str | None]:
    """Gitee profile：og:title + 嵌入 JSON 的 description/user-intro。"""
    emb = _embedded_json(text, ("description", "name", "bio"))
    title = _clean(_meta_content(text, "og:title")) or _title(text)
    # gitee og:title 形如 "张三 - Gitee.com"
    display_name = emb.get("name")
    if not display_name and title:
        m = re.match(r"^(.*?)\s*[-–—|]\s*Gitee", title, re.IGNORECASE)
        display_name = m.group(1).strip() if m else title
    return {
        "display_name": display_name,
        "bio": emb.get("description") or emb.get("bio")
        or _clean(_meta_content(text, "og:description", "description")),
        "company": None,
        "location": None,
    }


def _parse_weibo(text: str) -> dict[str, str | None]:
    """微博：WMN 的 uri_check 是 ajax/profile/info JSON，直接解析；HTML 则回退。"""
    t = text.strip()
    if t.startswith("{"):
        try:
            import json as _json
            data = _json.loads(t)
            user = (data.get("data") or {}).get("user") or data.get("user") or {}
            return {
                "display_name": user.get("screen_name") or user.get("name"),
                "bio": user.get("description"),
                "company": user.get("company") or user.get("verified_reason"),
                "location": user.get("location"),
            }
        except Exception:
            pass
    gen = _parse_generic(text)
    gen["display_name"] = gen["display_name"] or _clean(
        _meta_content(text, "og:nick_name")
    )
    return gen


def _parse_douban(text: str) -> dict[str, str | None]:
    """豆瓣 people 页：meta description = 简介；.signature 块为个人签名。"""
    sig = None
    m = re.search(
        r'class=["\']signature["\'][^>]*>(.*?)</div>',
        text, re.IGNORECASE | re.DOTALL,
    )
    if m:
        sig = _clean(m.group(1))
    title = _clean(_meta_content(text, "og:title")) or _title(text)
    return {
        "display_name": title,
        "bio": sig or _clean(_meta_content(text, "og:description", "description")),
        "company": None,
        "location": None,
    }


def _parse_zhihu(text: str) -> dict[str, str | None]:
    """知乎 people 页：嵌入 JSON 的 name/description/headline；JS 渲染页回退 meta。"""
    emb = _embedded_json(text, ("name", "description", "headline"))
    return {
        "display_name": emb.get("name")
        or _clean(_meta_content(text, "og:title"))
        or _title(text),
        "bio": emb.get("description")
        or _clean(_meta_content(text, "og:description", "description")),
        "company": emb.get("headline"),
        "location": None,
    }


# (name, url 匹配, parse)
_SITE_PARSERS: list[tuple[str, Callable[[str], bool], Callable[[str], dict]]] = [
    ("github", lambda u: "github.com/" in u, _parse_github),
    ("gitee", lambda u: "gitee.com/" in u, _parse_gitee),
    ("weibo", lambda u: "weibo.com/" in u, _parse_weibo),
    ("douban", lambda u: "douban.com/" in u, _parse_douban),
    ("zhihu", lambda u: "zhihu.com/" in u, _parse_zhihu),
]


def _guess_site(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    return host or "unknown"


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def extract_profile_metadata(html: Any, url: str) -> dict[str, Any]:
    """从 profile 页内容提取元数据。

    html: 页面 HTML（str/bytes）；微博 ajax 场景下可直接传 JSON 文本。
    url: 抓取该页面的 URL（用于命中专用解析器）。

    专用解析命中则其结果优先，空字段由通用 fallback 并补；
    无命中 → 纯通用 fallback。
    """
    url = url or ""
    text = _as_text(html)
    parser_name = "generic"
    base = _parse_generic(text)
    for name, match, parse in _SITE_PARSERS:
        try:
            if match(url.lower()):
                parser_name = name
                for k, v in parse(text).items():
                    # 专用解析站点调优、更懂本页：有值即覆盖通用 fallback
                    if v:
                        base[k] = v
                break
        except Exception:
            continue
    return {
        "site": _guess_site(url),
        "url": url,
        "display_name": base.get("display_name"),
        "bio": base.get("bio"),
        "company": base.get("company"),
        "location": base.get("location"),
        "parser": parser_name,
    }


def profile_text(pm: dict[str, Any]) -> str:
    """把 profile_metadata 拼成一段待挖掘文本（喂 contact_extractor）。"""
    if not isinstance(pm, dict):
        return ""
    parts = [
        pm.get("display_name"),
        pm.get("bio"),
        pm.get("company"),
        pm.get("location"),
    ]
    return "\n".join(p for p in parts if p)
