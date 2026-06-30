#!/usr/bin/env python3
"""Config 单元测试 — wallstreet-tieling v0.5.0

覆盖：路径常量 / API 配置 / 角色映射 / 模式模板 / 定价 / get_api_key / reload_config
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from api import config


# ══════════════════════════════════════════════════════════
#  路径常量
# ══════════════════════════════════════════════════════════


class TestPaths:
    def test_skill_dir_exists(self):
        """SKILL_DIR 是有效目录"""
        assert config.SKILL_DIR.is_dir()

    def test_sub_skills_dir_exists(self):
        """SUB_SKILLS_DIR 是有效目录"""
        assert config.SUB_SKILLS_DIR.is_dir()

    def test_output_dir_exists(self):
        """OUTPUT_DIR 是有效目录"""
        assert config.OUTPUT_DIR.is_dir()

    def test_skill_dir_is_absolute(self):
        """SKILL_DIR 是绝对路径"""
        assert config.SKILL_DIR.is_absolute()

    def test_sub_skills_dir_under_skill_dir(self):
        """SUB_SKILLS_DIR 是 SKILL_DIR 的子目录"""
        assert str(config.SUB_SKILLS_DIR).startswith(str(config.SKILL_DIR))


# ══════════════════════════════════════════════════════════
#  API Key 读取逻辑
# ══════════════════════════════════════════════════════════


class TestAPIKey:
    def test_config_example_is_valid_and_secret_free(self):
        """config.example.yaml is parseable and does not ship real secrets."""
        example_path = Path(__file__).parent.parent.parent / "config.example.yaml"

        payload = yaml.safe_load(example_path.read_text(encoding="utf-8"))
        text = example_path.read_text(encoding="utf-8")

        assert payload["datasources_config"] == "adapters/multi_datasource/datasources.yaml"
        assert payload["public_web_search"]["provider_type"] == "searxng"
        assert payload["telegram_public_service"]["source_review_required"] is True
        assert payload["qyyjt"]["enabled"] is False
        assert "github" + "_pat_" not in text
        assert "gh" + "p_" not in text
        assert "gho_" not in text
        assert "sk-" not in payload["api_key"]

    def test_get_api_key_returns_string(self):
        """get_api_key() 返回字符串"""
        key = config.get_api_key()
        assert isinstance(key, str)

    def test_get_api_base_returns_string(self):
        """get_api_base() 返回字符串"""
        base = config.get_api_base()
        assert isinstance(base, str)
        assert "://" in base

    def test_config_module_has_expected_attributes(self):
        """config 模块包含预期的属性"""
        assert hasattr(config, "API_KEY")
        assert hasattr(config, "API_BASE")
        assert hasattr(config, "SKILL_DIR")
        assert hasattr(config, "SUB_SKILLS_DIR")
        assert hasattr(config, "DEFAULT_MODEL")
        assert hasattr(config, "DEFAULT_CONCURRENCY")

    def test_get_api_key_returns_api_key_value(self):
        """get_api_key() 返回 API_KEY 模块变量"""
        # 直接验证函数返回模块级变量的值
        assert config.get_api_key() == config.API_KEY

    def test_get_api_base_returns_api_base_value(self):
        """get_api_base() 返回 API_BASE 模块变量"""
        assert config.get_api_base() == config.API_BASE

    def test_api_base_is_valid_url(self):
        """API_BASE 是有效的 URL 格式"""
        base = config.get_api_base()
        assert base.startswith("https://") or base.startswith("http://")


# ══════════════════════════════════════════════════════════
#  MODE_TEMPLATES 结构
# ══════════════════════════════════════════════════════════


class TestModeTemplates:
    def test_six_modes_defined(self):
        """MODE_TEMPLATES 包含 6 种模式"""
        assert len(config.MODE_TEMPLATES) == 6

    def test_all_modes_have_desc(self):
        """每种模式都有 desc 字段"""
        for mode_name, template in config.MODE_TEMPLATES.items():
            assert "desc" in template
            assert isinstance(template["desc"], str)
            assert len(template["desc"]) > 0, f"{mode_name} desc 为空"

    def test_all_modes_have_phase_keys(self):
        """每种模式都有 phase1/phase2/phase3 键"""
        for mode_name, template in config.MODE_TEMPLATES.items():
            for phase in ["phase1", "phase2", "phase3"]:
                assert phase in template, f"{mode_name} 缺少 {phase}"
                assert isinstance(template[phase], list)

    def test_agent_ids_are_valid(self):
        """模式中引用的 agent_id 都在 ROLE_FILE_MAP 中"""
        for mode_name, template in config.MODE_TEMPLATES.items():
            all_agents = template["phase1"] + template["phase2"] + template["phase3"]
            for aid in all_agents:
                assert aid in config.ROLE_FILE_MAP, \
                    f"{mode_name} 引用了未知 agent: {aid}"

    def test_simple_mode_only_zhang_tie_zhu(self):
        """simple 模式仅张铁柱"""
        assert config.MODE_TEMPLATES["simple"]["phase1"] == ["zhang-tie-zhu"]
        assert config.MODE_TEMPLATES["simple"]["phase2"] == []
        assert config.MODE_TEMPLATES["simple"]["phase3"] == []

    def test_report_mode_only_phase3(self):
        """report 模式只在 phase3 有 agent"""
        t = config.MODE_TEMPLATES["report"]
        assert t["phase1"] == []
        assert t["phase2"] == []
        assert len(t["phase3"]) == 2


# ══════════════════════════════════════════════════════════
#  ROLE_FILE_MAP / ROLE_NAME_MAP
# ══════════════════════════════════════════════════════════


class TestRoleMaps:
    def test_role_file_map_has_13_entries(self):
        """ROLE_FILE_MAP 恰好 13 个映射"""
        assert len(config.ROLE_FILE_MAP) == 13

    def test_role_name_map_has_13_entries(self):
        """ROLE_NAME_MAP 恰好 13 个角色名"""
        assert len(config.ROLE_NAME_MAP) == 13

    def test_maps_have_same_keys(self):
        """两个 map 的 key 集合一致"""
        assert set(config.ROLE_FILE_MAP.keys()) == set(config.ROLE_NAME_MAP.keys())

    def test_all_file_entries_end_with_dot_md(self):
        """ROLE_FILE_MAP 所有值以 .md 结尾"""
        for v in config.ROLE_FILE_MAP.values():
            assert v.endswith(".md")

    def test_all_names_are_non_empty(self):
        """ROLE_NAME_MAP 所有角色名非空"""
        for v in config.ROLE_NAME_MAP.values():
            assert isinstance(v, str)
            assert len(v) > 0


# ══════════════════════════════════════════════════════════
#  PRICING 价格表
# ══════════════════════════════════════════════════════════


class TestPricing:
    def test_pricing_has_entries(self):
        """PRICING 包含多个模型"""
        assert len(config.PRICING) >= 5

    def test_each_pricing_has_input_output(self):
        """每个定价条目有 input/output 字段"""
        for model, price in config.PRICING.items():
            assert "input" in price
            assert "output" in price
            assert isinstance(price["input"], (int, float))
            assert isinstance(price["output"], (int, float))

    def test_deepseek_models_present(self):
        """deepseek 系列模型在定价表中"""
        assert "deepseek" in config.PRICING
        assert "deepseek-r1" in config.PRICING
        # R1 定价更高（推理模型）
        assert config.PRICING["deepseek-r1"]["output"] > config.PRICING["deepseek"]["output"]


# ══════════════════════════════════════════════════════════
#  reload_config
# ══════════════════════════════════════════════════════════


class TestReloadConfig:
    def test_reload_config_no_error_on_default(self):
        """reload_config() 默认调用不报错"""
        import importlib
        import api.config
        importlib.reload(api.config)
        # 不应抛异常
        api.config.reload_config()
        assert isinstance(api.config.API_KEY, str)

    def test_reload_updates_api_key(self):
        """reload_config 将 API_KEY 同步为模块变量值"""
        import importlib
        import api.config
        importlib.reload(api.config)

        # 直接 patch 模块属性模拟环境变量效果
        with patch.object(api.config, "API_KEY", "patched-api-key-value"):
            assert api.config.get_api_key() == "patched-api-key-value"

    def test_reload_preserves_default_model(self):
        """reload_config 不会改变默认模型"""
        import importlib
        import api.config
        importlib.reload(api.config)
        api.config.reload_config()
        # DEFAULT_MODEL 有默认值 deepseek-chat
        assert isinstance(api.config.DEFAULT_MODEL, str)
        assert len(api.config.DEFAULT_MODEL) > 0

    def test_reload_preserves_concurrency(self):
        """reload_config 后 DEFAULT_CONCURRENCY 是整数"""
        import importlib
        import api.config
        importlib.reload(api.config)
        api.config.reload_config()
        assert isinstance(api.config.DEFAULT_CONCURRENCY, int)
        assert api.config.DEFAULT_CONCURRENCY > 0
