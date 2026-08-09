from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
SKILL_ROOT = ROOT / "skills" / "distill-medical-literature"


class LiteratureSkillContractTests(unittest.TestCase):
    def test_skill_encodes_verified_literature_distillation_chain(self):
        text = (SKILL_ROOT / "SKILL.md").read_text("utf-8")

        for required in (
            "name: distill-medical-literature",
            "为什么值得看",
            "研究问题",
            "研究怎么做",
            "统计方法",
            "主要发现",
            "这篇研究的新意",
            "科研设计启发",
            "证据边界",
            "等待用户确认",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_skill_rejects_advertising_and_false_novelty(self):
        text = (SKILL_ROOT / "SKILL.md").read_text("utf-8")

        for required in (
            "广告",
            "课程",
            "二维码",
            "复杂不等于创新",
            "不夸大可发表性",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_references_preserve_auditability_without_raw_articles(self):
        sources = (SKILL_ROOT / "references" / "source-manifest.md").read_text(
            "utf-8"
        )
        method = (SKILL_ROOT / "references" / "distillation-audit.md").read_text(
            "utf-8"
        )
        contract = (SKILL_ROOT / "references" / "output-contract.md").read_text(
            "utf-8"
        )
        metadata = (SKILL_ROOT / "agents" / "openai.yaml").read_text("utf-8")
        language_sources = (
            SKILL_ROOT / "references" / "language-source-manifest.md"
        ).read_text("utf-8")

        self.assertEqual(sources.count("https://mp.weixin.qq.com/s/"), 10)
        self.assertIn("RIA-TV++", method)
        self.assertIn("三重验证", method)
        self.assertIn("status: preview", contract)
        self.assertIn("evidence_level:", contract)
        self.assertIn("```mermaid", contract)
        self.assertIn("原论文图", contract)
        self.assertIn("$distill-medical-literature", metadata)
        self.assertEqual(language_sources.count("https://mp.weixin.qq.com/s/"), 32)

    def test_language_style_is_executable_not_a_brand_imitation(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text("utf-8")
        style = (SKILL_ROOT / "references" / "language-style.md").read_text(
            "utf-8"
        )
        contract = (SKILL_ROOT / "references" / "output-contract.md").read_text(
            "utf-8"
        )

        self.assertIn("language-style.md", skill)
        for required in (
            "场景 → 隐性代价 → 研究主张",
            "旧方法遗漏 → 新方法补足 → 直观类比 → 类比边界",
            "判断 → 依据 → 对决策的含义",
            "每段 2–4 句",
            "不复制来源的固定句式",
            "原始研究讲解",
        ):
            with self.subTest(required=required):
                self.assertIn(required, style)

        self.assertIn("语言自检", contract)
        self.assertIn("设问", contract)
        self.assertIn("装饰图", contract)
        self.assertIn("由文章内容决定类型", contract)

    def test_wechat_explainer_keeps_teaching_rhythm_and_article_led_novelty(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text("utf-8")
        style = (SKILL_ROOT / "references" / "language-style.md").read_text(
            "utf-8"
        )

        for required in (
            "只删除广告、引流和界面噪声",
            "保留原有讲解顺序、问题推进、口语节奏、有效类比和图文关系",
            "事实核对留在后台",
            "创新点必须从文章本身判断",
            "统计方法创新和暴露因素/指标创新",
            "不额外改造成审稿报告",
        ):
            with self.subTest(required=required):
                self.assertIn(required, skill)

        self.assertIn("一句提醒就够了", style)
        self.assertIn("不要在研究问题、方法、结果和结尾重复同一条限制", style)


if __name__ == "__main__":
    unittest.main()
