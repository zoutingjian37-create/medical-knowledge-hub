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
source_account: "示例医学统计号"
source_title: "童年经历与成年心血管病"
published_at: "2026-07-30"
evidence_level: public_account_summary
status: preview
wiki_updates: []
---

# 童年经历与成年心血管病

## 核心结论
童年不利经历可能通过成年抑郁影响心血管健康。

## 临床问题与 PICO/PECO
中老年人群中的童年暴露与心血管结局。

## 数据与变量
CHARLS、童年暴露、抑郁和心血管结局。

## 方法—问题映射
纵向生存分析与中介分析。

## 主要结论
关联和部分中介路径成立。

## 统计方法创新
方法应用创新：把中介分析用于生命周期问题。

## 其他创新点
生命周期暴露与心理路径的联合问题设计。

## 迁移方向
可迁移至其他早期暴露和慢性病结局。

## 潜在选题
灵感候选：睡眠是否参与相似路径。

## 证据边界
观察性关联不能证明因果关系。

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
            author="示例医学统计号",
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

    def test_wechat_skill_output_contract_matches_preview_validator(self):
        from extensions.processing.compiler import REQUIRED_SECTIONS

        contract = (
            Path(__file__).parents[1]
            / "skills"
            / "distill-medical-wechat"
            / "references"
            / "output-contract.md"
        ).read_text("utf-8")

        for section in REQUIRED_SECTIONS:
            self.assertIn(f"## {section}", contract)

    def test_handoff_references_source_without_copying_article_body(self):
        result = self._compiler().prepare_handoff(self.job.id)

        handoff = result.handoff_path.read_text("utf-8")
        self.assertIn("$distill-medical-wechat", handoff)
        self.assertIn(SOURCE_URL, handoff)
        self.assertNotIn("只允许临时保存的清洗后正文", handoff)
        self.assertIn(result.mode, {"desktop", "cli"})
        self.assertEqual("handoff_ready", self.store.get(self.job.id).status)

    def test_literature_job_uses_the_literature_skill(self):
        self.store.update(self.job.id, platform="literature")

        result = self._compiler().prepare_handoff(self.job.id)

        handoff = result.handoff_path.read_text("utf-8")
        self.assertIn("$distill-medical-literature", handoff)
        self.assertNotIn("$distill-medical-wechat", handoff)

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

    def test_validator_accepts_the_current_installed_skill_section_contract(self):
        current = (
            _preview()
            .replace("## 研究问题与 PECO", "## 临床问题与 PICO/PECO")
            .replace("## 数据来源和关键变量", "## 数据与变量")
            .replace("## 分析方法概览", "## 方法—问题映射")
            .replace("## 主要结论与结果", "## 主要结论")
            .replace("## 创新点与前沿方法雷达", "## 统计方法创新\n方法应用创新。\n\n## 其他创新点")
            .replace("## 可迁移元素", "## 迁移方向")
            .replace("## 潜在选题", "## 证据边界\n观察性证据。\n\n## 潜在选题")
        )

        accepted = self._compiler().accept_preview(self.job.id, current, [])
        self.assertEqual("preview_ready", accepted.status)

    def test_trash_hides_job_without_deleting_local_artifacts(self):
        compiler = self._compiler()
        compiler.accept_preview(self.job.id, _preview(), [])

        trashed = compiler.trash(self.job.id)

        self.assertEqual("trashed", trashed.status)
        self.assertEqual("preview_ready", trashed.status_before_trash)
        self.assertTrue(trashed.deleted_at)
        self.assertTrue(Path(self.job.cache_path).exists())
        self.assertTrue(Path(trashed.preview_path).exists())
        self.assertEqual((), self.store.list())
        self.assertEqual((trashed,), self.store.list_trash())

    def test_restore_returns_a_trashed_job_to_its_previous_status(self):
        compiler = self._compiler()
        compiler.accept_preview(self.job.id, _preview(), [])
        compiler.trash(self.job.id)

        restored = compiler.restore(self.job.id)

        self.assertEqual("preview_ready", restored.status)
        self.assertEqual("", restored.deleted_at)
        self.assertEqual("", restored.status_before_trash)
        self.assertEqual((restored,), self.store.list())

    def test_permanent_delete_removes_only_local_job_artifacts(self):
        compiler = self._compiler()
        compiler.accept_preview(self.job.id, _preview(), [])
        handoff = compiler.prepare_handoff(self.job.id).handoff_path
        trashed = compiler.trash(self.job.id)
        self.assertTrue(handoff.exists())

        compiler.delete_permanently(self.job.id)

        self.assertFalse(Path(trashed.cache_path).exists())
        self.assertFalse(Path(trashed.preview_path).exists())
        self.assertFalse(handoff.exists())
        with self.assertRaises(KeyError):
            self.store.get(self.job.id)
        self.assertEqual([], list(self.vault.rglob("*.md")))

    def test_bulk_permanent_delete_validates_all_jobs_before_removal(self):
        from extensions.processing.compiler import PreviewValidationError

        compiler = self._compiler()
        compiler.trash(self.job.id)
        second = self.store.create(
            MarkdownDocument(
                source_url="https://example.org/second",
                title="第二篇",
                author="示例来源",
                published_at="2026-08-01",
                markdown="第二篇临时正文。",
            ),
            self.cache.put("second", "第二篇临时正文。"),
            job_id="second",
        )

        with self.assertRaises(PreviewValidationError):
            compiler.delete_permanently_many([self.job.id, second.id])

        self.assertEqual("trashed", self.store.get(self.job.id).status)
        self.assertEqual("pending", self.store.get(second.id).status)

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

    def test_api_moves_jobs_to_trash_restores_and_permanently_deletes_them(self):
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
            moved = client.post(f"/api/ext/knowledge/jobs/{self.job.id}/trash")
            active = client.get("/api/ext/knowledge/jobs")
            trash = client.get("/api/ext/knowledge/trash")
            setting = client.put(
                "/api/ext/knowledge/trash/settings",
                json={"retention_days": 30},
            )
            purged = client.post("/api/ext/knowledge/trash/purge", json={})
            workflow = client.put(
                "/api/ext/knowledge/settings",
                json={"auto_distill": False},
            )
            restored = client.post(
                f"/api/ext/knowledge/jobs/{self.job.id}/restore"
            )
            client.post(f"/api/ext/knowledge/jobs/{self.job.id}/trash")
            deleted = client.delete(f"/api/ext/knowledge/jobs/{self.job.id}")
            empty_trash = client.get("/api/ext/knowledge/trash")

        self.assertEqual(200, moved.status_code)
        self.assertEqual([], active.json()["jobs"])
        self.assertEqual(self.job.id, trash.json()["jobs"][0]["id"])
        self.assertEqual(7, trash.json()["retention_days"])
        self.assertEqual(30, setting.json()["retention_days"])
        self.assertEqual(0, purged.json()["count"])
        self.assertFalse(workflow.json()["auto_distill"])
        self.assertEqual("pending", restored.json()["job"]["status"])
        self.assertEqual(204, deleted.status_code)
        self.assertEqual([], empty_trash.json()["jobs"])

    def test_api_permanently_deletes_selected_recycled_jobs(self):
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
            client.post(f"/api/ext/knowledge/jobs/{self.job.id}/trash")
            restored = client.post(
                "/api/ext/knowledge/trash/restore-selected",
                json={"job_ids": [self.job.id]},
            )
            moved = client.post(
                "/api/ext/knowledge/jobs/trash-selected",
                json={"job_ids": [self.job.id]},
            )
            response = client.post(
                "/api/ext/knowledge/trash/delete-selected",
                json={"job_ids": [self.job.id, self.job.id]},
            )
            trash = client.get("/api/ext/knowledge/trash")

        self.assertEqual(1, restored.json()["count"])
        self.assertEqual(1, moved.json()["count"])
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.json()["count"])
        self.assertEqual([], trash.json()["jobs"])

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

    def test_api_approves_selected_ready_previews(self):
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
            client.post(
                f"/api/ext/knowledge/jobs/{self.job.id}/preview",
                json={"markdown": _preview(), "wiki_updates": []},
            )
            response = client.post(
                "/api/ext/knowledge/jobs/approve-selected",
                json={"job_ids": [self.job.id]},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.json()["count"])
        self.assertEqual("approved", self.store.get(self.job.id).status)

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
        self.assertIn("统计方法创新", response.json()["markdown"])
        self.assertNotIn("cache_path", response.text)


if __name__ == "__main__":
    unittest.main()
