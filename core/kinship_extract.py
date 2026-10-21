#!/usr/bin/env python3
"""亲属关系表述抽取（公开文本）—— 亲属关系 lane 共享抽取层。

覆盖 survey 路径：
  1. 招股书 / 年报 / 上市公司公告（巨潮资讯 cninfo）—— evidence_level="exact"
  2. 裁判文书全文（browser-assisted 粘贴）—— evidence_level="strong"
  3. 公开报道 / 讣告（人工粘贴文本；实时新闻源按红线判死，无在线抓取）
  4. 当事人自曝（公开社交简介 / 个人介绍）—— evidence_level="review"

全部为纯函数，无网络 IO。输出一律是 leads（线索），措辞只能是
"披露显示 / 文书载明 / 自述 / 疑似"，绝不断言亲属关系为事实。

relation_kind:
  spouse         夫妻
  parent_child   父母子女
  sibling        兄弟姐妹
  inferred_family 其他亲属（翁婿 / 叔侄 / 舅甥 / 祖孙 / 表亲 / 泛称"亲属"等）

evidence_level: exact（法定披露原文）/ strong（文书载明）/ review（推理或自述）
"""

from __future__ import annotations

import re
from typing import Any

RELATION_KINDS = ("spouse", "parent_child", "sibling", "inferred_family")
EVIDENCE_LEVELS = ("exact", "strong", "review")

KIND_CN = {
    "spouse": "夫妻关系",
    "parent_child": "父母子女关系",
    "sibling": "兄弟姐妹关系",
    "inferred_family": "亲属关系",
}

# 关系词 -> relation_kind
_REL_WORD_KIND = {
    "夫妻": "spouse", "妻": "spouse", "夫": "spouse",
    "妻子": "spouse", "丈夫": "spouse", "配偶": "spouse",
    "老公": "spouse", "老婆": "spouse", "爱人": "spouse",
    "父子": "parent_child", "母子": "parent_child",
    "父女": "parent_child", "母女": "parent_child",
    "父": "parent_child", "母": "parent_child",
    "子": "parent_child", "女": "parent_child",
    "父亲": "parent_child", "母亲": "parent_child",
    "儿子": "parent_child", "女儿": "parent_child",
    "爸爸": "parent_child", "妈妈": "parent_child",
    "兄弟": "sibling", "姐妹": "sibling",
    "兄妹": "sibling", "姐弟": "sibling",
    "兄": "sibling", "弟": "sibling", "姐": "sibling", "妹": "sibling",
    "哥哥": "sibling", "弟弟": "sibling", "姐姐": "sibling", "妹妹": "sibling",
}

# 扩展亲属词 -> inferred_family
_EXTENDED_KIN = (
    "翁婿", "婆媳", "叔侄", "舅甥", "祖孙", "岳父", "岳母",
    "儿媳", "女婿", "亲家", "连襟", "妯娌", "表亲", "堂亲",
    "亲属", "家属", "亲戚",
)

_NAME = r"[\u4e00-\u9fa5]{2,4}"

# 姓名候选停用词：组织/职务/公告常用词，避免把"有限公司"之类当成人名
_NAME_STOPWORDS = frozenset({
    "公司", "有限", "股份", "集团", "控股", "实业", "科技", "发展",
    "公告", "报告", "关系", "夫妻", "兄弟", "姐妹", "父子", "母子",
    "父女", "母女", "配偶", "亲属", "家属", "自然人", "关联",
    "一致", "行动", "股东", "董事", "监事", "法人", "经理", "先生",
    "女士", "妻子", "丈夫", "父亲", "母亲", "儿子", "女儿",
    "哥哥", "弟弟", "姐姐", "妹妹", "信息", "披露", "义务",
    "有限合伙", "合伙", "企业",
})

_KIN_WORDS_IN_NAME = frozenset(
    list(_REL_WORD_KIND.keys()) + list(_EXTENDED_KIN)
)


# 组织/职务残片：人名不可能包含这些（防"张三之子公司"把"公司持有"当人名）
_ORG_FRAGMENTS = frozenset({
    "公司", "有限", "股份", "集团", "控股", "企业", "合伙", "持有",
    "实业", "科技", "发展", "投资", "管理", "中心",
})


def _clean_name(raw: str) -> str:
    """姓名候选清洗：去停用词 / 去含亲属词或组织残片的候选。"""
    name = (raw or "").strip()
    if not name or len(name) < 2 or len(name) > 4:
        return ""
    if name in _NAME_STOPWORDS:
        return ""
    for w in _KIN_WORDS_IN_NAME:
        if w in name:
            return ""
    for frag in _ORG_FRAGMENTS:
        if frag in name:
            return ""
    # 称谓后缀（张三先生 -> 张三）
    for suffix in ("先生", "女士", "董事长", "总裁"):
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
    # 诉讼角色前缀（原告张三 -> 张三）
    for prefix in ("原告", "被告", "上诉人", "被上诉人", "第三人",
                   "申请执行人", "被执行人", "申请人", "被申请人"):
        if name.startswith(prefix) and len(name) > len(prefix):
            name = name[len(prefix):]
            break
    if not name or len(name) < 2:
        return ""
    return name


def _candidate_names(sentence: str, exclude: set[str] | None = None) -> list[str]:
    """句子中的候选人名（2-4 个汉字，停用词过滤），按出现顺序去重。

    先把亲属词/系词/虚词替换为空格再切分，避免 finditer 把"李四为翁"
    这类跨词片段贪婪吞成"人名"。
    """
    exclude = exclude or set()
    tmp = sentence
    for w in sorted(_KIN_WORDS_IN_NAME, key=len, reverse=True):
        tmp = tmp.replace(w, " ")
    for p in ("系", "为", "与", "和", "及", "之", "的", "其", "该",
              "本人", "夫妇", "关系"):
        tmp = tmp.replace(p, " ")
    out: list[str] = []
    for chunk in re.split(r"[^\u4e00-\u9fa5]+", tmp):
        name = _clean_name(chunk)
        if name and name not in exclude and name not in out:
            out.append(name)
    return out


# 裸 b3 捕获（"张三之妻李四现任董事"）的动词尾巴：命中则剥离
_VERB_TAILS = ("现任", "曾任", "担任", "出任", "兼任", "现为", "已成", "已故",
               "现年", "系", "为", "与", "和", "及", "并", "现", "曾", "任",
               "已", "故")


def _trim_verb_tail(name: str) -> str:
    for tail in _VERB_TAILS:
        if name.endswith(tail) and len(name) - len(tail) >= 2:
            return name[: -len(tail)]
    return name


# -- 结构化模式（高精度，带命名捕获） ------------------------------------
# 条目：(正则, kind 指定或 "rel", 是否回指型)
# 回指型（"其妻李四"/"配偶：李四"）：A 缺失时可用 focus_name 回填，
# 因为"其/该"在语篇中必有所指。

_STRUCTURED_PATTERNS: list[tuple[re.Pattern[str], str, bool]] = [
    # 张三与李四系夫妻关系 / 张三、李四系父子关系 / 张三和李四为兄弟关系
    (re.compile(
        rf"(?P<a>{_NAME})[与和及、](?P<b>{_NAME})[系为]"
        r"(?P<rel>夫妻|父子|母子|父女|母女|兄弟|姐妹|兄妹|姐弟)关系"),
     "rel", False),
    # 李四系张三之妻 / 王五系赵六之子
    (re.compile(
        rf"(?P<b>{_NAME})系(?P<a>{_NAME})之"
        r"(?P<rel>妻|夫|父|母|子|女|兄|弟|姐|妹)"),
     "rel", False),
    # 张三之妻李四 / 张三之子（李四）
    (re.compile(
        rf"(?P<a>{_NAME})之(?P<rel>妻|夫|父|母|子|女|兄|弟|姐|妹)"
        rf"(?:（(?P<b>{_NAME})）|[(（](?P<b2>{_NAME})[)）]|(?P<b3>{_NAME}))?"),
     "rel", False),
    # 张三的妻子李四 / 张三的父亲（李四）
    (re.compile(
        rf"(?P<a>{_NAME})的(?P<rel>妻子|丈夫|父亲|母亲|儿子|女儿|哥哥|弟弟|姐姐|妹妹|配偶)"
        rf"(?:（(?P<b>{_NAME})）|[(（](?P<b2>{_NAME})[)）]|(?P<b3>{_NAME}))?"),
     "rel", False),
    # 其妻李四 / 其子（李四）/ 该女李四（回指）
    (re.compile(
        r"(?:其|该)(?:长|次)?(?P<rel>妻|夫|父|母|子|女|兄|弟|姐|妹|妻子|丈夫|父亲|母亲|儿子|女儿|哥哥|弟弟|姐姐|妹妹)"
        rf"(?:（(?P<b>{_NAME})）|[(（](?P<b2>{_NAME})[)）]|(?P<b3>{_NAME}))?"),
     "rel", True),
    # 张三、李四夫妇
    (re.compile(rf"(?P<a>{_NAME})[、，,](?P<b>{_NAME})夫妇"), "spouse", False),
    # 配偶：李四 / 配偶为李四（回指，A 由 focus_name 补）
    (re.compile(rf"配偶[:：为是\s]+(?P<b>{_NAME})"), "spouse", True),
]

# 松散句级关键词（需人名归因）：词 -> kind
_LOOSE_KEYWORDS: list[tuple[str, str]] = [
    ("夫妻", "spouse"), ("配偶", "spouse"),
    ("父子", "parent_child"), ("母子", "parent_child"),
    ("父女", "parent_child"), ("母女", "parent_child"),
    ("兄弟", "sibling"), ("姐妹", "sibling"),
    ("兄妹", "sibling"), ("姐弟", "sibling"),
] + [(w, "inferred_family") for w in _EXTENDED_KIN]

# 夫妻店 / 兄弟公司等固定搭配：出现即整句降级为噪音（不抽取）
_NOISE_PHRASES = ("夫妻店", "兄弟公司", "姐妹公司", "兄弟单位", "兄弟院校", "父子公司")


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"[。！？\n；;]+", text or "")
    return [p.strip() for p in parts if p.strip()]


def _rel_kind(rel_word: str) -> str:
    return _REL_WORD_KIND.get(rel_word, "inferred_family")


def _mk_statement(person_a: str, person_b: str, kind: str,
                 evidence_level: str, quote: str,
                 source_ref: str) -> dict[str, Any] | None:
    a = _clean_name(person_a)
    b = _clean_name(person_b)
    if not a or not b or a == b:
        return None
    if kind not in RELATION_KINDS:
        return None
    return {
        "person_a": a,
        "person_b": b,
        "relation_kind": kind,
        "evidence_level": evidence_level,
        "quote": quote[:180],
        "source_ref": (source_ref or "")[:200],
    }


def extract_kinship_statements(
    text: str,
    focus_name: str | None = None,
    evidence_level: str = "exact",
    source_ref: str = "",
) -> list[dict[str, Any]]:
    """从公开文本中抽取亲属关系表述。

    Args:
        text: 公告 / 文书 / 报道正文（纯文本）。
        focus_name: 关注人名（2-4 汉字）；出现在句中时作为归因锚点。
        evidence_level: exact（法定披露原文）/ strong（文书载明）/ review。
        source_ref: 来源标注（如公告标题 / 文书案号），随 statement 返回。

    Returns:
        kinship statement 列表（去重），每条含 person_a/person_b/
        relation_kind/evidence_level/quote/source_ref。
    """
    if evidence_level not in EVIDENCE_LEVELS:
        raise ValueError("evidence_level must be one of {}".format(EVIDENCE_LEVELS))
    focus = _clean_name(focus_name or "")
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def _emit(st: dict[str, Any] | None) -> None:
        if not st:
            return
        key = (st["relation_kind"],
               min(st["person_a"], st["person_b"]),
               max(st["person_a"], st["person_b"]))
        if key in seen:
            return
        seen.add(key)
        out.append(st)

    for sent in _split_sentences(text):
        if any(noise in sent for noise in _NOISE_PHRASES):
            continue
        quote = sent if len(sent) <= 180 else sent[:177] + "…"

        # -- Stage A: 结构化模式 --
        for pat, kind_spec, anaphoric in _STRUCTURED_PATTERNS:
            for m in pat.finditer(sent):
                gd = m.groupdict()
                rel_word = gd.get("rel") or ""
                kind = kind_spec if kind_spec in RELATION_KINDS else _rel_kind(rel_word)
                a = _clean_name(gd.get("a") or "")
                b_raw = gd.get("b") or gd.get("b2") or ""
                b = _clean_name(b_raw)
                if not b and gd.get("b3"):
                    # 裸名捕获（"张三之妻李四现任董事"）：剥离动词尾巴
                    b = _clean_name(_trim_verb_tail(gd.get("b3") or ""))
                if not a and focus and (anaphoric or focus in sent):
                    # "其妻李四" / "配偶：李四"：A 为关注人（回指）
                    a = focus
                if not a or not b:
                    continue
                _emit(_mk_statement(a, b, kind, evidence_level, quote, source_ref))

        # -- Stage B: 松散关键词 + 人名归因（需 focus 或句中恰好两人名） --
        for kw, kind in _LOOSE_KEYWORDS:
            if kw not in sent:
                continue
            # 避免把"兄弟公司"这类漏网之鱼算入（结构化阶段已处理大部分）
            names = _candidate_names(sent)
            if focus and focus in sent:
                others = [n for n in names
                          if n != focus and focus not in n and n not in focus]
                if len(others) == 1 and len(names) <= 2:
                    _emit(_mk_statement(focus, others[0], kind,
                                        evidence_level, quote, source_ref))
            elif len(names) == 2 and not any(
                    s["quote"] == quote for s in out):
                _emit(_mk_statement(names[0], names[1], kind,
                                    evidence_level, quote, source_ref))
    return out


# -- 当事人自曝（公开简介 / 个人介绍） ------------------------------------

_SELF_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # "张三的妻子" / "李四的老公"（A 为资料主人，B 为具名亲属）
    (re.compile(
        rf"(?P<b>{_NAME})的(?P<rel>妻子|丈夫|儿子|女儿|老公|老婆|父亲|母亲|爸爸|妈妈|哥哥|弟弟|姐姐|妹妹)"),
     "rel"),
    # "本人系张三之妻"
    (re.compile(
        rf"(?:本人|我)系(?P<b>{_NAME})之(?P<rel>妻|夫|父|母|子|女|兄|弟|姐|妹)"),
     "rel"),
]


def extract_self_claimed_kinship(
    bio_text: str,
    profile_name: str | None = None,
) -> list[dict[str, Any]]:
    """从公开个人简介中抽取亲属自述（如"张三的妻子"）。

    evidence_level 固定为 "review"（自述，低置信度）。
    person_a 为资料主人（profile_name，未知时为空字符串，由调用方回填）。
    """
    profile = _clean_name(profile_name or "")
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for sent in _split_sentences(bio_text):
        quote = sent if len(sent) <= 180 else sent[:177] + "…"
        for pat, kind_spec in _SELF_PATTERNS:
            for m in pat.finditer(sent):
                gd = m.groupdict()
                kind = _rel_kind(gd.get("rel") or "")
                b = _clean_name(gd.get("b") or "")
                if not b:
                    continue
                key = (kind, profile, b)
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "person_a": profile,
                    "person_b": b,
                    "relation_kind": kind,
                    "evidence_level": "review",
                    "quote": quote,
                    "source_ref": "profile_bio",
                })
    return out


def statement_note(st: dict[str, Any]) -> str:
    """措辞 guard：只允许 披露显示 / 文书载明 / 自述 / 疑似，绝不断言。"""
    a = st.get("person_a") or "?"
    b = st.get("person_b") or "?"
    kind_cn = KIND_CN.get(st.get("relation_kind") or "", "亲属关系")
    src = st.get("source_ref") or ""
    src_suffix = "（{}）".format(src[:80]) if src else ""
    level = st.get("evidence_level")
    if level == "exact":
        head = "披露显示"
    elif level == "strong":
        head = "文书载明"
    else:
        head = "自述/疑似"
    tail = "" if level == "exact" else "，待核实"
    return "{}：{}{}系{}{}{}".format(head, a, "与" + b if b != "?" else "", kind_cn, tail, src_suffix)
