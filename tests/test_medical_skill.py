from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
SKILL_ROOT = ROOT / "skills" / "distill-medical-wechat"


class MedicalSkillContractTests(unittest.TestCase):
    def test_skill_encodes_approved_distillation_rules(self):
        text = (SKILL_ROOT / "SKILL.md").read_text("utf-8")

        for required in (
            "创新点与前沿方法雷达",
            "方法学原创",
            "方法应用创新",
            "高级方法使用",
            "不默认记录效应值",
            "不审校公众号讲解",
            "至少三篇",
            "等待用户确认",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_skill_has_reusable_output_contract_and_ui_metadata(self):
        contract = (
            SKILL_ROOT / "references" / "output-contract.md"
        ).read_text("utf-8")
        metadata = (SKILL_ROOT / "agents" / "openai.yaml").read_text("utf-8")

        self.assertIn("verification_level: public-account", contract)
        self.assertIn("status: preview", contract)
        self.assertIn("wiki_updates: []", contract)
        self.assertIn("$distill-medical-wechat", metadata)


if __name__ == "__main__":
    unittest.main()
