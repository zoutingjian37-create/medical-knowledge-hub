from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
SKILL_ROOT = ROOT / "skills" / "distill-medical-literature"


class LiteratureSkillContractTests(unittest.TestCase):
    def test_skill_encodes_verified_literature_distillation_chain(self):
        text = (SKILL_ROOT / "SKILL.md").read_text("utf-8")

        for required in (
            "name: distill-medical-literature",
            "临床问题",
            "PICO/PECO",
            "数据与变量",
            "方法—问题映射",
            "主要结论",
            "统计方法创新",
            "其他创新点",
            "迁移方向",
            "潜在选题",
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
            "不是创新",
            "复杂不等于创新",
            "不得声称可直接立项",
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

        self.assertEqual(sources.count("https://mp.weixin.qq.com/s/"), 10)
        self.assertIn("RIA-TV++", method)
        self.assertIn("三重验证", method)
        self.assertIn("status: preview", contract)
        self.assertIn("evidence_level:", contract)
        self.assertIn("$distill-medical-literature", metadata)


if __name__ == "__main__":
    unittest.main()
