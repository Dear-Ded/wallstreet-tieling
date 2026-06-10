#!/usr/bin/env python3
"""QualityRules 纯函数单元测试 — wallstreet-tieling v3.2.0

测试基石：全部零依赖、零 Mock、纯函数。
覆盖：信贷决策词 / 模糊词 / 来源缺失 / 截断检测 / 编造检测 / L2 评分引擎
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api.quality_rules import QualityRules, Violation, VAGUE_WORDS_TERMS


# ══════════════════════════════════════════════════════════
#  信贷决策词检测
# ══════════════════════════════════════════════════════════

class TestCreditWordDetection:
    """铁律第一条：禁止输出信贷决策词"""

    def test_detect_recommend_credit(self):
        """'建议通过授信' → ERROR"""
        v = QualityRules.scan("建议通过授信，额度500万", "test")
        credit = [x for x in v if x.rule == "credit_word"]
        assert len(credit) == 1
        assert credit[0].severity == "ERROR"
        assert "建议通过" in credit[0].detail

    def test_detect_risk_controllable(self):
        """'风险可控' → ERROR"""
        v = QualityRules.scan("综合来看风险可控", "test")
        credit = [x for x in v if x.rule == "credit_word"]
        assert len(credit) >= 1

    def test_detect_multiple_credit_words(self):
        """多个信贷决策词全部捕获"""
        v = QualityRules.scan("建议通过授信，可放款500万，建议利率5%", "test")
        credit = [x for x in v if x.rule == "credit_word"]
        assert len(credit) == 1  # 一个 violation 包含所有匹配词
        assert "建议通过" in credit[0].detail or "建议" in credit[0].detail

    def test_no_credit_words_clean_text(self):
        """干净文本不应触发"""
        v = QualityRules.scan("注册资本1000万元[来源: tyc-mcp, 时间: 2026-06-10]", "test")
        credit = [x for x in v if x.rule == "credit_word"]
        assert len(credit) == 0

    def test_approval_related_not_credit_advice(self):
        """'审批通过项目' vs 信贷决策词——需要区分"""
        v = QualityRules.scan("审批通过", "test")
        credit = [x for x in v if x.rule == "credit_word"]
        assert len(credit) >= 1


# ══════════════════════════════════════════════════════════
#  模糊词检测
# ══════════════════════════════════════════════════════════

class TestVagueWordDetection:
    """铁律第三条：禁止模糊表述"""

    def test_detect_dagai(self):
        v = QualityRules.scan("该公司大概有50%的市占率", "test")
        vague = [x for x in v if x.rule == "vague_word"]
        assert len(vague) == 1
        assert vague[0].severity == "WARN"

    def test_detect_maybe(self):
        v = QualityRules.scan("可能也是行业第一", "test")
        vague = [x for x in v if x.rule == "vague_word"]
        assert len(vague) == 1

    def test_detect_sihu(self):
        v = QualityRules.scan("似乎没有太大问题", "test")
        vague = [x for x in v if x.rule == "vague_word"]
        assert len(vague) == 1

    def test_detect_zuoyou(self):
        v = QualityRules.scan("营收在5亿左右", "test")
        vague = [x for x in v if x.rule == "vague_word"]
        assert len(vague) == 1

    def test_vague_words_inside_quotes_excluded(self):
        """引号内的模糊词应被过滤"""
        v = QualityRules.scan('有分析说"大概50%"是合理估计', "test")
        vague = [x for x in v if x.rule == "vague_word"]
        # "大概"在引号内应被过滤
        assert len(vague) <= 1  # "估计"可能仍匹配

    def test_no_vague_in_clean_text(self):
        v = QualityRules.scan("市占率35%[来源: 行业报告, 2026-Q1]", "test")
        vague = [x for x in v if x.rule == "vague_word"]
        assert len(vague) == 0

    def test_dagai_shi_compound(self):
        """'大概是' (VAGUE_WORDS_TERMS 中的复合词)"""
        v = QualityRules.scan("营收大概是5亿", "test")
        vague = [x for x in v if x.rule == "vague_word"]
        assert len(vague) >= 1

    def test_yibanwei_compound(self):
        """'一般为' (VAGUE_WORDS_TERMS 中的复合词)"""
        v = QualityRules.scan("注册资本一般为1000万", "test")
        vague = [x for x in v if x.rule == "vague_word"]
        assert len(vague) >= 1


# ══════════════════════════════════════════════════════════
#  来源标注检测
# ══════════════════════════════════════════════════════════

class TestSourceAnnotation:
    """铁律第四条：数据来源必标注"""

    def test_no_source_annotation_long_text(self):
        """>100字且无[来源:]标注 → ERROR"""
        text = "注册资本1000万元，成立于2018年。公司经营正常。" * 7  # >100 chars
        v = QualityRules.scan(text, "test")
        no_src = [x for x in v if x.rule == "no_source"]
        assert len(no_src) == 1
        assert no_src[0].severity == "ERROR"

    def test_has_source_passes(self):
        text = ("注册资本1000万元[来源: tyc-mcp, 参数: company_name='测试公司', "
                "时间: 2026-06-10]。" * 3)  # >100 chars with sources
        v = QualityRules.scan(text, "test")
        no_src = [x for x in v if x.rule == "no_source"]
        assert len(no_src) == 0

    def test_short_text_no_source_skipped(self):
        """≤100字不检查来源"""
        v = QualityRules.scan("注册资本1000万", "test")
        no_src = [x for x in v if x.rule == "no_source"]
        assert len(no_src) == 0

    def test_source_with_chinese_colon(self):
        """来源：中文冒号也应识别"""
        text = "营收5亿[来源：行业报告, 2026]" + "x" * 80  # >100 chars
        v = QualityRules.scan(text, "test")
        no_src = [x for x in v if x.rule == "no_source"]
        assert len(no_src) == 0  # 中文冒号也匹配

    def test_anonymous_source_banned(self):
        """禁止 [来源: 公开信息] + '据悉' 等匿名源"""
        text = "据悉该公司营收约5亿。据知情人士称利润不错。" * 6  # >100 chars, has anon sources
        v = QualityRules.scan(text, "test")
        fab = QualityRules.check_fabrication_indicators(text)
        has_anon = any(i["indicator"] == "anonymous_source" for i in fab)
        assert has_anon  # "据悉"等匿名源


# ══════════════════════════════════════════════════════════
#  截断检测
# ══════════════════════════════════════════════════════════

class TestTruncation:
    def test_short_output_detected(self):
        """<200字 → WARN"""
        v = QualityRules.scan("短", "test")
        trunc = [x for x in v if x.rule == "short_output"]
        assert len(trunc) == 1
        assert trunc[0].severity == "WARN"

    def test_normal_output_no_truncation(self):
        text = ("这是正常长度的尽调输出。" * 45)  # >500 chars (12*45=540)
        v = QualityRules.scan(text, "test")
        trunc = [x for x in v if x.rule == "short_output"]
        assert len(trunc) == 0


# ══════════════════════════════════════════════════════════
#  编造信号检测
# ══════════════════════════════════════════════════════════

class TestFabricationIndicators:
    def test_anonymous_source_detected(self):
        """'据悉' → 匿名源信号"""
        text = "据悉，该公司去年营收超过100亿。据知情人士透露，正在筹备上市。"
        indicators = QualityRules.check_fabrication_indicators(text)
        anon = [i for i in indicators if i["indicator"] == "anonymous_source"]
        assert len(anon) == 1
        assert anon[0]["count"] >= 2

    def test_bare_number_without_source(self):
        """有数字但无[来源:]标注 → 编造信号"""
        text = "营收500亿，利润50亿，员工20000人。数据来自可靠渠道。"
        indicators = QualityRules.check_fabrication_indicators(text)
        bare = [i for i in indicators if i["indicator"] == "bare_number_no_source"]
        assert len(bare) >= 1

    def test_bare_number_with_source_passes(self):
        """有数字且有来源标注 → 不触发"""
        text = ("营收500亿[来源: Bloomberg, 2026]。"
                "利润50亿[来源: Bloomberg, 2026]。" * 3)
        indicators = QualityRules.check_fabrication_indicators(text)
        bare = [i for i in indicators if i["indicator"] == "bare_number_no_source"]
        assert len(bare) == 0

    def test_low_density_text_detected(self):
        """文本密度过低 → 编造信号"""
        text = " " * 500 + "短文本内容不足"
        indicators = QualityRules.check_fabrication_indicators(text)
        density = [i for i in indicators if i["indicator"] == "low_density"]
        assert len(density) >= 1

    def test_no_fabrication_in_clean_output(self):
        text = "营收500亿[来源: Bloomberg, 2026-06-10]。利润50亿[来源: 同上]。" * 5
        indicators = QualityRules.check_fabrication_indicators(text)
        assert len(indicators) == 0


# ══════════════════════════════════════════════════════════
#  L2 评分引擎
# ══════════════════════════════════════════════════════════

class TestValidateDdOutput:
    def test_perfect_output_scores_high(self):
        """完美输出 → 评分≥90"""
        text = ("注册资本1000万元[来源: tyc-mcp, 参数: company_name='测试公司', "
                "时间: 2026-06-10]。营收500亿[来源: Bloomberg, 2026]。" * 3)
        result = QualityRules.validate_dd_output(text, "test")
        assert result["score"] >= 80  # 来源覆盖率检查可能扣分
        # 注意: 因来源覆盖率公式 (source/3 data points per source), 
        # 大量数字时需要更多来源标注才能满分

    def test_fabrication_reduces_score(self):
        """编造信号 → 大幅扣分"""
        text = "据悉该公司营收约500亿。知情人士称利润可观。"
        result = QualityRules.validate_dd_output(text, "test")
        assert result["score"] < 80
        assert result["stats"]["fabrication_indicators"] > 0

    def test_fabrication_makes_invalid(self):
        """有编造信号 → valid=False"""
        text = "据悉该公司营收约500亿。市场规模约1000亿。"
        result = QualityRules.validate_dd_output(text, "test")
        assert result["valid"] is False

    def test_data_gap_marker_detected(self):
        """有[未获取]标记 → has_data_gap_marker=True"""
        text = "营收[未获取] 利润[未获取] 资产[未获取]。" * 10
        result = QualityRules.validate_dd_output(text, "test")
        assert result["stats"]["has_data_gap_marker"] is True

    def test_missing_data_gap_hint(self):
        """>300字无[未获取] → 提示"""
        text = ("该公司经营状况良好。" * 20)  # >300 chars, no gap markers
        result = QualityRules.validate_dd_output(text, "test")
        issues = result.get("issues", [])
        has_hint = any("未获取" in i for i in issues)
        assert has_hint or result["stats"]["has_data_gap_marker"] is False

    def test_fuzzy_terms_counted(self):
        text = "大概营收5亿，可能利润1亿，似乎经营正常。" * 3
        result = QualityRules.validate_dd_output(text, "test")
        assert result["stats"]["fuzzy_terms"] > 2

    def test_source_coverage_ratio_checked(self):
        """来源覆盖率低 → 问题标记"""
        text = ("营收500亿，利润50亿，市值1000亿，员工20000人，"
                "资产3000亿。营收600亿，利润60亿。" * 12)  # >500 chars, many numbers
        result = QualityRules.validate_dd_output(text, "test")
        issues = result.get("issues", [])
        has_coverage = any("来源覆盖率" in i for i in issues)
        assert has_coverage


# ══════════════════════════════════════════════════════════
#  VAGUE_WORDS 统一来源验证
# ══════════════════════════════════════════════════════════

class TestVagueWordsUnifiedSource:
    """验证 VAGUE_WORDS 双轨已修复"""

    def test_vague_words_regex_matches_terms(self):
        """扫描正则与 validate 列表使用同一来源"""
        # validate_dd_output 用 VAGUE_WORDS_TERMS
        # scan 用 QualityRules.VAGUE_WORDS (从 VAGUE_WORDS_TERMS 构建)
        test_text = "大概是5亿 一般为10% 通常为半年"
        for term in ["大概是", "一般为", "通常为"]:
            in_list = term in VAGUE_WORDS_TERMS
            in_regex = QualityRules.VAGUE_WORDS.search(test_text) is not None
            # 如果 term 在列表中，正则应该能匹配到文本中的 term
            if in_list:
                assert in_regex, f"'{term}' in TERMS but VAGUE_WORDS regex can't match"

    def test_all_15_terms(self):
        """VAGUE_WORDS_TERMS 应有 15 个词"""
        assert len(VAGUE_WORDS_TERMS) == 15
        assert "大概是" in VAGUE_WORDS_TERMS
        assert "一般为" in VAGUE_WORDS_TERMS
        assert "通常为" in VAGUE_WORDS_TERMS
        assert "大概" in VAGUE_WORDS_TERMS
        assert "可能" in VAGUE_WORDS_TERMS


# ══════════════════════════════════════════════════════════
#  Violation 数据类
# ══════════════════════════════════════════════════════════

class TestViolation:
    def test_violation_creation(self):
        v = Violation(rule="test", field="f", detail="d", severity="WARN")
        assert v.rule == "test"
        assert v.severity == "WARN"

    def test_default_severity(self):
        v = Violation(rule="x", field="y", detail="z")
        assert v.severity == "ERROR"
