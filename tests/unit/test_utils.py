#!/usr/bin/env python3
"""Utils 单元测试 — wallstreet-tieling v0.5.0

覆盖：slug / load_skill / load_system_prompt / extract_numbers_with_unit / extract_company_ids
"""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api.utils import (
    slug,
    load_skill,
    load_system_prompt,
    extract_numbers_with_unit,
    extract_company_ids,
)
from api import config


# ══════════════════════════════════════════════════════════
#  slug
# ══════════════════════════════════════════════════════════


class TestSlug:
    def test_chinese_text(self):
        """中文文本保留中文字符"""
        result = slug("张铁柱的尽调报告")
        assert "张铁柱" in result
        assert "的" in result
        assert "尽" in result

    def test_english_text(self):
        """英文文本转换特殊字符为连字符"""
        result = slug("Hello World")
        assert "Hello" in result
        assert "-" in result or "World" in result

    def test_mixed_chinese_english(self):
        """中英混合"""
        result = slug("华尔街 wallstreet 2024")
        assert "华尔街" in result
        assert "wallstreet" in result
        assert "2024" in result

    def test_special_chars_replaced_with_dash(self):
        """特殊字符被替换为 -"""
        result = slug("test!@#$%^&*()string")
        # 标点符号被替换为 -
        assert "-" in result
        assert "test" in result
        assert "string" in result

    def test_consecutive_dashes_collapsed(self):
        """连续 - 合并为单个"""
        result = slug("a!!!b")
        assert "--" not in result
        assert "a" in result
        assert "b" in result

    def test_empty_string_returns_unknown(self):
        """空字符串 → unknown"""
        result = slug("")
        assert result == "unknown"

    def test_only_special_chars_returns_unknown(self):
        """全特殊字符 → unknown"""
        result = slug("!@#$%")
        assert result == "unknown"

    def test_truncation_at_max_len(self):
        """超过 max_len 被截断"""
        long_text = "a" * 80
        result = slug(long_text, max_len=40)
        assert len(result) == 40

    def test_default_max_len_40(self):
        """默认 max_len=40"""
        long_text = "x" * 100
        result = slug(long_text)
        assert len(result) == 40

    def test_strips_leading_trailing_dashes(self):
        """去除首尾 - """
        result = slug("!hello!")
        # slug("!hello!") → "-hello-" → strip → "hello"
        assert not result.startswith("-")
        assert not result.endswith("-")


# ══════════════════════════════════════════════════════════
#  load_skill
# ══════════════════════════════════════════════════════════


class TestLoadSkill:
    @pytest.fixture
    def temp_skill_file(self):
        """创建临时 skill 文件"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        ) as f:
            f.write("# 测试角色\n测试技能内容。")
            skill_path = Path(f.name)
        yield skill_path
        skill_path.unlink(missing_ok=True)

    def test_load_existing_skill(self, temp_skill_file):
        """存在的文件 → 读取内容"""
        with patch.object(config, "SUB_SKILLS_DIR", temp_skill_file.parent):
            content = load_skill(temp_skill_file.name)
            assert "# 测试角色" in content
            assert "测试技能内容" in content

    def test_load_nonexistent_skill_fallback(self):
        """不存在的文件 → fallback 字符串"""
        with patch.object(config, "SUB_SKILLS_DIR", Path("/nonexistent/path")):
            content = load_skill("nobody.md")
            assert "nobody" in content
            assert "角色定义缺失" in content

    def test_fallback_contains_filename_without_ext(self):
        """fallback 消息包含文件名（不含扩展名）"""
        with patch.object(config, "SUB_SKILLS_DIR", Path("/nonexistent/xyz")):
            content = load_skill("test-role.md")
            assert "test-role" in content


# ══════════════════════════════════════════════════════════
#  load_system_prompt
# ══════════════════════════════════════════════════════════


class TestLoadSystemPrompt:
    @pytest.fixture
    def temp_skill_dir(self):
        """创建临时目录，内含 SKILL.md"""
        tmpdir = Path(tempfile.mkdtemp())
        skill_md = tmpdir / "SKILL.md"
        skill_md.write_text("# WallStreet Tieling\n系统提示词内容。", encoding="utf-8")
        yield tmpdir
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_load_existing_system_prompt(self, temp_skill_dir):
        """SKILL.md 存在 → 读取内容"""
        with patch.object(config, "SKILL_DIR", temp_skill_dir):
            content = load_system_prompt()
            assert "WallStreet Tieling" in content
            assert "系统提示词内容" in content

    def test_load_nonexistent_system_prompt_fallback(self):
        """SKILL.md 不存在 → 默认提示词"""
        with patch.object(config, "SKILL_DIR", Path("/nonexistent")):
            content = load_system_prompt()
            assert "尽调专家" in content
            assert "不给建议" in content


# ══════════════════════════════════════════════════════════
#  extract_numbers_with_unit
# ══════════════════════════════════════════════════════════


class TestExtractNumbersWithUnit:
    def test_extract_yi(self):
        """提取'亿'单位匹配的数字"""
        result = extract_numbers_with_unit("营收500亿，利润50亿")
        # 正则只捕获数字组 (\d{2,}(?:\.\d+)?)，单位在非捕获组中
        assert "500" in result
        assert "50" in result

    def test_extract_wan(self):
        """提取'万'单位"""
        result = extract_numbers_with_unit("员工20000万人")
        assert len(result) >= 1

    def test_extract_percent(self):
        """提取%匹配的数字"""
        result = extract_numbers_with_unit("利润率15%，增长率8.5%")
        # 捕获组只返回数字
        assert "15" in result or "8.5" in result

    def test_extract_decimal_numbers(self):
        """提取带小数点的数字"""
        result = extract_numbers_with_unit("市值123.45亿")
        assert len(result) >= 1
        # 至少包含数字
        assert any("123.45" in r for r in result)

    def test_extract_single_digit(self):
        r"""v0.5.0: 个位数也会被提取（修复 #21 遗漏"5亿"等表达）"""
        result = extract_numbers_with_unit("营收5亿增长50%")
        # 个位数现在也被匹配（正则改为 \d+ 而非 \d{2,}）
        assert "5" in result
        assert "50" in result

    def test_empty_text(self):
        """空文本 → 空列表"""
        assert extract_numbers_with_unit("") == []

    def test_no_numbers_with_unit(self):
        """无数字+单位 → 空列表"""
        assert extract_numbers_with_unit("这是纯文本描述") == []

    def test_multiple_units_mixed(self):
        """混合多种单位"""
        result = extract_numbers_with_unit("营收500亿，利润50%，员工20000人，估值1000万")
        assert len(result) >= 3


# ══════════════════════════════════════════════════════════
#  extract_company_ids
# ══════════════════════════════════════════════════════════


class TestExtractCompanyIds:
    def test_extract_tyc_mcp_id(self):
        """tyc-mcp 格式"""
        result = extract_company_ids('tyc-mcp cid="abc123"')
        assert len(result) == 1
        assert result[0]["source"] == "extracted"
        assert result[0]["id"] == "abc123"

    def test_extract_qcc_company_id(self):
        """qcc-company 格式"""
        result = extract_company_ids("qcc-company cid=xyz789")
        assert len(result) == 1
        assert result[0]["id"] == "xyz789"

    def test_extract_multiple_ids(self):
        """多个 ID"""
        text = "tyc-mcp cid=111 qcc-company cid=222 tyc-mcp cid=333"
        result = extract_company_ids(text)
        assert len(result) == 3
        ids = [r["id"] for r in result]
        assert ids == ["111", "222", "333"]

    def test_empty_text_returns_empty(self):
        """空文本 → 空列表"""
        assert extract_company_ids("") == []

    def test_no_ids_returns_empty(self):
        """没有 company_id → 空列表"""
        assert extract_company_ids("这是一段没有ID的普通文本") == []

    def test_case_insensitive(self):
        """大小写不敏感"""
        result = extract_company_ids("TYC-MCP cid=CASE123")
        assert len(result) == 1
        assert result[0]["id"] == "CASE123"

    def test_ids_with_colon_format(self):
        """cid: 格式（冒号）"""
        result = extract_company_ids('qcc-company cid:"abc"')
        assert len(result) == 1
        assert result[0]["id"] == "abc"
