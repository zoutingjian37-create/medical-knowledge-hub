import tempfile
import unittest
from pathlib import Path

from extensions.processing.documents import MarkdownDocument
from extensions.processing.job_queue import KnowledgeJobQueue
from extensions.processing.job_store import KnowledgeJobStore
from extensions.processing.source_cache import SourceCache


SOURCE_URL = "https://mp.weixin.qq.com/s/clean-preview-example"


class WeChatCleanPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.cache = SourceCache(root / "cache")
        self.store = KnowledgeJobStore(root / "state")
        self.vault = root / "vault"
        document = MarkdownDocument(
            source_url=SOURCE_URL,
            title="竞争风险模型入门",
            author="示例医学公众号",
            published_at="2026-05-01",
            markdown=(
                "# 竞争风险模型入门\n\n"
                "> 公众号：示例医学公众号\n\n---\n\n"
                "这是正文第一段，原有论证顺序应当保留。\n\n"
                "![研究流程图](https://mmbiz.qpic.cn/example/figure.png)\n\n"
                "这是正文第二段，解释什么时候使用竞争风险模型。\n\n"
                "扫码报名课程\n\n![报名二维码](https://mmbiz.qpic.cn/example/ad.png)"
            ),
        )
        queue = KnowledgeJobQueue(cache=self.cache, store=self.store)
        self.job = queue.enqueue(document, platform="wechat").job

    def tearDown(self):
        self.temporary.cleanup()

    def _compiler(self):
        from extensions.processing.compiler import KnowledgeCompiler

        return KnowledgeCompiler(store=self.store, cache=self.cache)

    def test_code_generates_clean_preview_without_distillation_sections(self):
        preview_job = self._compiler().prepare_clean_preview(self.job.id)
        markdown = Path(preview_job.preview_path).read_text("utf-8")

        self.assertEqual("preview_ready", preview_job.status)
        self.assertIn("这是正文第一段", markdown)
        self.assertIn("这是正文第二段", markdown)
        self.assertIn("![研究流程图]", markdown)
        self.assertNotIn("扫码报名课程", markdown)
        self.assertNotIn("报名二维码", markdown)
        self.assertNotIn("## PICO", markdown)
        self.assertNotIn("## 创新点", markdown)
        self.assertIn("status: preview", markdown)
        self.assertIn("状态：等待用户确认", markdown)
        self.assertEqual((), preview_job.wiki_updates)

    def test_approved_wechat_article_uses_wechat_folder(self):
        self._compiler().prepare_clean_preview(self.job.id)

        result = self._compiler().approve(self.job.id, self.vault)

        self.assertEqual("微信公众号", result.knowledge_card.parent.name)
        self.assertTrue(result.knowledge_card.exists())

    def test_pure_student_case_promotion_is_not_queued(self):
        document = MarkdownDocument(
            source_url="https://mp.weixin.qq.com/s/pure-promotion-example",
            title="总IF=11.8！学员一周发表五篇SCI，他们做了什么？",
            author="示例医学公众号",
            published_at="2026-08-02",
            markdown="恭喜学员接收，报名后一对一指导，关注菜单咨询方案。",
        )

        result = KnowledgeJobQueue(cache=self.cache, store=self.store).enqueue(
            document, platform="wechat"
        )

        self.assertFalse(result.queued)
        self.assertEqual("advertisement", result.reason)

    def test_inline_follow_and_consultation_blocks_are_removed(self):
        from extensions.processing.archive import clean_markdown

        markdown = (
            "# Logistic、Cox 与竞争风险模型\n\n---\n\n"
            "本号由示例团队所创，欢迎关注！10年科研指导经验，1v1指导发表SCI。\n\n"
            "Logistic 回归回答结局是否发生，Cox 回归同时利用随访时间和删失信息。"
            "当存在互斥结局时，应根据研究目的选择原因别风险或 Fine-Gray 模型。\n\n"
            "关注—点菜单栏【SCI指导】—1V1咨询方案\n\n"
            "![三类模型选择流程图](https://mmbiz.qpic.cn/example/method.png)"
        )

        cleaned = clean_markdown(markdown)

        self.assertNotIn("欢迎关注", cleaned)
        self.assertNotIn("1V1咨询方案", cleaned)
        self.assertIn("Logistic 回归回答", cleaned)
        self.assertIn("![三类模型选择流程图]", cleaned)

    def test_high_impact_factor_method_article_is_not_treated_as_promotion(self):
        document = MarkdownDocument(
            source_url="https://mp.weixin.qq.com/s/high-if-method-example",
            title="医学顶刊 IF=28：目标试验模拟方法讲解",
            author="示例医学公众号",
            published_at="2026-08-02",
            markdown=(
                "本文说明目标试验模拟的研究设计、变量定义和统计模型。\n\n"
                "研究结果提示该方法可以降低不死时间偏倚。"
            ),
        )

        result = KnowledgeJobQueue(cache=self.cache, store=self.store).enqueue(
            document, platform="wechat"
        )

        self.assertTrue(result.queued)

    def test_promotion_dense_body_is_rejected_even_with_neutral_title(self):
        document = MarkdownDocument(
            source_url="https://mp.weixin.qq.com/s/promotion-dense-example",
            title="本周科研资讯汇总",
            author="示例医学公众号",
            published_at="2026-08-02",
            markdown=(
                "恭喜数据库学员一次投中并成功接收。\n\n"
                "课程报名后可加入学习群，领取全部资料。\n\n"
                "关注菜单栏并添加老师，咨询1V1指导方案。\n\n"
                "扫码报名课程，限时优惠。"
            ),
        )

        result = KnowledgeJobQueue(cache=self.cache, store=self.store).enqueue(
            document, platform="wechat"
        )

        self.assertFalse(result.queued)
        self.assertEqual("advertisement", result.reason)

    def test_advertisement_rules_are_account_agnostic(self):
        body = (
            "恭喜学员论文成功接收。\n\n"
            "课程报名后可以加入学习群。\n\n"
            "关注菜单栏并咨询一对一指导方案。\n\n"
            "扫码报名课程，领取限时优惠。"
        )
        queue = KnowledgeJobQueue(cache=self.cache, store=self.store)

        results = [
            queue.enqueue(
                MarkdownDocument(
                    source_url=f"https://mp.weixin.qq.com/s/account-agnostic-{index}",
                    title="本周消息汇总",
                    author=account,
                    published_at="2026-08-02",
                    markdown=body,
                ),
                platform="wechat",
            )
            for index, account in enumerate(("示例健康研究", "演示统计学习"), 1)
        ]

        self.assertEqual(["advertisement", "advertisement"], [item.reason for item in results])
        self.assertTrue(all(not item.queued for item in results))

    def test_generic_tool_promotion_is_removed_without_a_named_teacher_rule(self):
        from extensions.processing.archive import clean_markdown

        markdown = (
            "研究采用多变量回归模型，并报告校准、区分度和外部验证结果。"
            "这些信息用于判断模型是否适合迁移到新的临床人群。\n\n"
            "本团队提供科研工具平台，点击领取并免费使用。"
        )

        cleaned = clean_markdown(markdown)

        self.assertIn("多变量回归模型", cleaned)
        self.assertNotIn("点击领取", cleaned)
        archive_source = (Path(__file__).parents[1] / "extensions/processing/archive.py").read_text("utf-8")
        self.assertNotIn("郑老师", archive_source)

    def test_reclean_many_updates_useful_preview_and_trashes_legacy_promotion(self):
        promotional = MarkdownDocument(
            source_url="https://mp.weixin.qq.com/s/legacy-promotion-example",
            title="总IF=9.6！学员一周接收四篇SCI",
            author="示例医学公众号",
            published_at="2026-08-02",
            markdown="恭喜学员接收，课程报名后加入学习群，关注菜单咨询1V1方案。",
        )
        legacy_id = self.store.id_for_source(promotional.source_url)
        legacy_job = self.store.create(
            promotional,
            self.cache.put(legacy_id, promotional.markdown),
            job_id=legacy_id,
            platform="wechat",
        )
        self.store.update(legacy_job.id, status="preview_ready")

        jobs = self._compiler().reclean_many([legacy_job.id, self.job.id])

        by_id = {job.id: job for job in jobs}
        self.assertEqual("trashed", by_id[legacy_job.id].status)
        self.assertEqual("advertisement", by_id[legacy_job.id].error)
        self.assertEqual("preview_ready", by_id[self.job.id].status)
        cleaned = Path(by_id[self.job.id].preview_path).read_text("utf-8")
        self.assertNotIn("扫码报名课程", cleaned)
        self.assertIn("![研究流程图]", cleaned)


if __name__ == "__main__":
    unittest.main()
