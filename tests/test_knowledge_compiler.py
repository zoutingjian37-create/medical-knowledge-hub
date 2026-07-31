import os
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from extensions.processing.documents import MarkdownDocument
from extensions.processing.job_store import KnowledgeJobStore
from extensions.processing.source_cache import SourceCache


SOURCE_URL = "https://mp.weixin.qq.com/s?__biz=demo&mid=2&idx=1&sn=y"


def _preview(source_url=SOURCE_URL):
    return f"""---
source_url: "{source_url}"
source_platform: wechat
source_account: "统计之光医学统计"
source_title: "童年经历与成年心血管病"
published_at: "2026-07-30"
verification_level: public-account
status: preview
wiki_updates: []
---

# 童年经历与成年心血管病

## 核心结论
童年不利经历可能通过成年抑郁影响心血管健康。

## 研究问题与 PECO
中老年人群中的童年暴露与心血管结局。

## 数据来源和关键变量
CHARLS、童年暴露、抑郁和心血管结局。

## 分析方法概览
纵向生存分析与中介分析。

## 主要结论与结果
关联和部分中介路径成立。

## 创新点与前沿方法雷达
方法应用创新：把中介分析用于生命周期问题。

## 可迁移元素
可迁移至其他早期暴露和慢性病结局。

## 潜在选题
灵感候选：睡眠是否参与相似路径。

## Wiki 更新建议
更新 CHARLS 与因果中介分析。

## 来源
{source_url}

状态：等待用户确认
"""


class KnowledgeCompilerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.cache = SourceCache(root / "cache")
        self.store = KnowledgeJobStore(root / "state")
        self.vault = root / "vault"
        document = MarkdownDocument(
            source_url=SOURCE_URL,
            title="童年经历与成年心血管病",
            author="统计之光医学统计",
            published_at="2026-07-30",
            markdown="这是只允许临时保存的清洗后正文。",
        )
        job_id = self.store.id_for_source(document.source_url)
        self.job = self.store.create(
            document,
            self.cache.put(job_id, document.markdown),
            job_id=job_id,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def _compiler(self):
        from extensions.processing.compiler import KnowledgeCompiler

        return KnowledgeCompiler(store=self.store, cache=self.cache)

    def test_handoff_references_source_without_copying_article_body(self):
        result = self._compiler().prepare_handoff(self.job.id)

        handoff = result.handoff_path.read_text("utf-8")
        self.assertIn("$distill-medical-wechat", handoff)
        self.assertIn(SOURCE_URL, handoff)
        self.assertNotIn("只允许临时保存的清洗后正文", handoff)
        self.assertIn(result.mode, {"desktop", "cli"})
        self.assertEqual("handoff_ready", self.store.get(self.job.id).status)

    def test_handoff_uses_configured_vault_page_list(self):
        page = self.vault / "研究要素" / "CHARLS.md"
        page.parent.mkdir(parents=True)
        page.write_text("# CHARLS\n", "utf-8")

        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(self.vault)}):
            result = self._compiler().prepare_handoff(self.job.id)

        handoff = result.handoff_path.read_text("utf-8")
        self.assertIn("研究要素/CHARLS.md", handoff)

    def test_handoff_does_not_offer_raw_source_cards_as_wiki_targets(self):
        broad = self.vault / "研究要素" / "CHARLS.md"
        source = self.vault / "微信公众号" / "某篇文章.md"
        evidence = self.vault / "证据卡" / "某篇知识卡.md"
        for page in (broad, source, evidence):
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(f"# {page.stem}\n", "utf-8")

        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(self.vault)}):
            result = self._compiler().prepare_handoff(self.job.id)

        handoff = result.handoff_path.read_text("utf-8")
        self.assertIn("研究要素/CHARLS.md", handoff)
        self.assertNotIn("微信公众号/某篇文章.md", handoff)
        self.assertNotIn("证据卡/某篇知识卡.md", handoff)

    def test_imports_preview_written_by_codex_to_the_handoff_output(self):
        compiler = self._compiler()
        handoff = compiler.prepare_handoff(self.job.id)
        generated = _preview().replace(
            "wiki_updates: []",
            "wiki_updates:\n  - 研究要素/CHARLS.md",
        )
        handoff.output_path.write_text(generated, "utf-8")

        imported = compiler.import_preview(self.job.id)

        self.assertEqual("preview_ready", imported.status)
        self.assertEqual(("研究要素/CHARLS.md",), imported.wiki_updates)

    def test_codex_cli_generates_and_imports_a_reviewable_preview(self):
        executable = Path(self.temporary.name) / "codex.exe"
        executable.write_bytes(b"")
        commands = []

        def run_process(command, **kwargs):
            commands.append((command, kwargs))
            output = self.store.root / "previews" / f"{self.job.id}.md"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(_preview(), "utf-8")
            return subprocess.CompletedProcess(command, 0, "completed", "")

        from extensions.processing.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(
            store=self.store,
            cache=self.cache,
            codex_executable=executable,
            process_runner=run_process,
        )
        compiled = compiler.run_codex(self.job.id)

        self.assertEqual("preview_ready", compiled.status)
        command, options = commands[0]
        self.assertEqual(str(executable), command[0])
        self.assertIn("exec", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("workspace-write", command)
        self.assertIn(str(self.cache.root), command)
        self.assertFalse(options["shell"])
        self.assertNotIn("只允许临时保存的清洗后正文", " ".join(command))

    def test_codex_cli_failure_is_visible_and_can_be_retried(self):
        executable = Path(self.temporary.name) / "codex.exe"
        executable.write_bytes(b"")

        def run_process(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, "", "login required")

        from extensions.processing.compiler import (
            CodexExecutionError,
            KnowledgeCompiler,
        )

        compiler = KnowledgeCompiler(
            store=self.store,
            cache=self.cache,
            codex_executable=executable,
            process_runner=run_process,
        )
        with self.assertRaises(CodexExecutionError):
            compiler.run_codex(self.job.id)

        failed = self.store.get(self.job.id)
        self.assertEqual("failed", failed.status)
        self.assertIn("login required", failed.error)

    def test_preview_does_not_change_vault(self):
        compiler = self._compiler()

        compiler.accept_preview(
            self.job.id,
            _preview(),
            ["研究要素/CHARLS.md", "前沿方法/因果中介分析.md"],
        )

        self.assertEqual([], list(self.vault.rglob("*.md")))
        self.assertEqual("preview_ready", self.store.get(self.job.id).status)

    def test_approve_writes_knowledge_updates_wiki_and_deletes_source_cache(self):
        compiler = self._compiler()
        compiler.accept_preview(
            self.job.id,
            _preview(),
            ["研究要素/CHARLS.md", "前沿方法/因果中介分析.md"],
        )

        result = compiler.approve(self.job.id, self.vault)

        self.assertTrue(result.knowledge_card.exists())
        self.assertIn(SOURCE_URL, result.knowledge_card.read_text("utf-8"))
        self.assertTrue((self.vault / "研究要素" / "CHARLS.md").exists())
        self.assertTrue((self.vault / "系统" / "log.md").exists())
        self.assertFalse(Path(self.job.cache_path).exists())
        self.assertEqual("approved", self.store.get(self.job.id).status)

    def test_narrow_single_article_pattern_is_rejected_as_new_wiki_page(self):
        from extensions.processing.compiler import PreviewValidationError

        with self.assertRaises(PreviewValidationError):
            self._compiler().accept_preview(
                self.job.id,
                _preview(),
                ["研究范式/生命早期暴露—心理中介—成年疾病.md"],
            )

    def test_raw_source_and_system_folders_cannot_be_wiki_update_targets(self):
        from extensions.processing.compiler import PreviewValidationError

        for target in ("微信公众号/某篇文章.md", "证据卡/某篇卡.md", "系统/log.md"):
            with self.subTest(target=target), self.assertRaises(PreviewValidationError):
                self._compiler().accept_preview(self.job.id, _preview(), [target])

    def test_preview_requires_matching_source_and_all_sections(self):
        from extensions.processing.compiler import PreviewValidationError

        with self.assertRaises(PreviewValidationError):
            self._compiler().accept_preview(
                self.job.id,
                "# 缺少结构的结果",
                [],
            )

    def test_reject_deletes_temporary_source_without_writing_vault(self):
        rejected = self._compiler().reject(self.job.id)

        self.assertEqual("rejected", rejected.status)
        self.assertFalse(Path(self.job.cache_path).exists())
        self.assertEqual([], list(self.vault.rglob("*.md")))

    def test_api_lists_jobs_without_exposing_temporary_cache_path(self):
        from fastapi.testclient import TestClient
        from app import app

        with (
            patch.dict(
                os.environ,
                {
                    "CONTENT_HUB_CACHE_DIR": str(self.cache.root),
                    "CONTENT_HUB_STATE_DIR": str(self.store.root),
                    "OBSIDIAN_VAULT_PATH": str(self.vault),
                },
            ),
            TestClient(app) as client,
        ):
            response = client.get("/api/ext/knowledge/jobs")

        self.assertEqual(200, response.status_code)
        self.assertEqual(self.job.id, response.json()["jobs"][0]["id"])
        self.assertNotIn("cache_path", response.text)

    def test_api_accepts_preview_and_requires_confirmation_before_write(self):
        from fastapi.testclient import TestClient
        from app import app

        with (
            patch.dict(
                os.environ,
                {
                    "CONTENT_HUB_CACHE_DIR": str(self.cache.root),
                    "CONTENT_HUB_STATE_DIR": str(self.store.root),
                    "OBSIDIAN_VAULT_PATH": str(self.vault),
                },
            ),
            TestClient(app) as client,
        ):
            preview = client.post(
                f"/api/ext/knowledge/jobs/{self.job.id}/preview",
                json={
                    "markdown": _preview(),
                    "wiki_updates": ["研究要素/CHARLS.md"],
                },
            )
            before_approval = list(self.vault.rglob("*.md"))
            approval = client.post(
                f"/api/ext/knowledge/jobs/{self.job.id}/approve"
            )

        self.assertEqual(200, preview.status_code)
        self.assertEqual([], before_approval)
        self.assertEqual(200, approval.status_code)
        self.assertTrue(Path(approval.json()["knowledge_card"]).exists())

    def test_api_imports_preview_created_at_handoff_output_path(self):
        handoff = self._compiler().prepare_handoff(self.job.id)
        handoff.output_path.write_text(_preview(), "utf-8")
        from fastapi.testclient import TestClient
        from app import app

        with (
            patch.dict(
                os.environ,
                {
                    "CONTENT_HUB_CACHE_DIR": str(self.cache.root),
                    "CONTENT_HUB_STATE_DIR": str(self.store.root),
                    "OBSIDIAN_VAULT_PATH": str(self.vault),
                },
            ),
            TestClient(app) as client,
        ):
            response = client.post(
                f"/api/ext/knowledge/jobs/{self.job.id}/import-preview"
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("preview_ready", response.json()["job"]["status"])

    def test_api_can_run_codex_and_return_a_preview_ready_job(self):
        from fastapi.testclient import TestClient
        from app import app
        from extensions.processing.compiler import KnowledgeCompiler

        def compile_job(compiler, job_id):
            return compiler.accept_preview(job_id, _preview(), [])

        with (
            patch.dict(
                os.environ,
                {
                    "CONTENT_HUB_CACHE_DIR": str(self.cache.root),
                    "CONTENT_HUB_STATE_DIR": str(self.store.root),
                    "OBSIDIAN_VAULT_PATH": str(self.vault),
                },
            ),
            patch.object(KnowledgeCompiler, "run_codex", autospec=True, side_effect=compile_job),
            TestClient(app) as client,
        ):
            response = client.post(
                f"/api/ext/knowledge/jobs/{self.job.id}/compile"
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("preview_ready", response.json()["job"]["status"])

    def test_api_returns_reviewable_preview_without_cache_metadata(self):
        self._compiler().accept_preview(self.job.id, _preview(), [])
        from fastapi.testclient import TestClient
        from app import app

        with (
            patch.dict(
                os.environ,
                {
                    "CONTENT_HUB_CACHE_DIR": str(self.cache.root),
                    "CONTENT_HUB_STATE_DIR": str(self.store.root),
                },
            ),
            TestClient(app) as client,
        ):
            response = client.get(
                f"/api/ext/knowledge/jobs/{self.job.id}/preview"
            )

        self.assertEqual(200, response.status_code)
        self.assertIn("创新点与前沿方法雷达", response.json()["markdown"])
        self.assertNotIn("cache_path", response.text)


if __name__ == "__main__":
    unittest.main()
