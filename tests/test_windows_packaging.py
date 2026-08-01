from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).parents[1]


class WindowsPackagingTests(unittest.TestCase):
    def test_release_manifest_can_be_read_from_an_extracted_zip_without_git(self):
        from release_manifest import build_manifest

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "static").mkdir()
            (root / "app.py").write_text("app = object()", "utf-8")
            (root / "static" / "subscriptions.html").write_text("ok", "utf-8")
            (root / ".env").write_text("SECRET=private", "utf-8")

            manifest = build_manifest(root)

        self.assertIn("app.py", manifest)
        self.assertIn("static/subscriptions.html", manifest)
        self.assertNotIn(".env", manifest)

    def test_release_manifest_includes_runtime_and_excludes_private_data(self):
        from release_manifest import build_manifest

        manifest = build_manifest(ROOT)

        self.assertIn("app.py", manifest)
        self.assertIn("skills/distill-medical-literature/SKILL.md", manifest)
        self.assertIn("skills/distill-medical-wechat/SKILL.md", manifest)
        self.assertIn("install-automation-task.ps1", manifest)
        self.assertIn("extensions/subscriptions/worker.py", manifest)
        self.assertIn("install.ps1", manifest)
        self.assertIn("launch.ps1", manifest)
        self.assertIn("Dockerfile", manifest)
        self.assertIn("start.sh", manifest)
        self.assertIn("status.sh", manifest)
        self.assertIn("assets/medical-knowledge-hub.ico", manifest)
        self.assertIn("docs/CODEX_REPRODUCTION.md", manifest)
        self.assertIn("PRODUCT.md", manifest)
        self.assertNotIn(".env", manifest)
        self.assertFalse(any(path.startswith("data/") for path in manifest))
        self.assertFalse(any(path.startswith("tests/") for path in manifest))
        self.assertFalse(any("__pycache__" in path for path in manifest))

    def test_installer_uses_d_drive_and_installs_skill_and_shortcut(self):
        installer = (ROOT / "install.ps1").read_text("utf-8")

        self.assertIn(r"D:\Codex\medical-knowledge-hub", installer)
        self.assertIn(r"D:\Codex\venvs\medical-knowledge-hub", installer)
        self.assertIn("distill-medical-literature", installer)
        self.assertIn("distill-medical-wechat", installer)
        self.assertIn("CONTENT_HUB_MANAGE_TASK_SCHEDULER", installer)
        self.assertIn("install-automation-task.ps1", installer)
        self.assertIn("CreateShortcut", installer)
        self.assertIn("start.bat", installer)
        self.assertIn("$Shortcut.TargetPath = $Launcher", installer)
        self.assertIn("$Shortcut.IconLocation = $Icon", installer)
        self.assertIn("ie4uinit.exe", installer)
        self.assertNotIn("$Shortcut.TargetPath = $PowerShell", installer)
        self.assertIn("[switch]$SkipWeChatDiscovery", installer)
        self.assertNotIn("[bool]$InstallWeChatDiscovery", installer)
        self.assertNotIn("Remove-Item -Recurse -Force $HOME", installer)

    def test_desktop_icon_contains_multiple_windows_sizes(self):
        icon = ROOT / "assets" / "medical-knowledge-hub.ico"
        data = icon.read_bytes()

        self.assertEqual(b"\x00\x00\x01\x00", data[:4])
        self.assertGreaterEqual(int.from_bytes(data[4:6], "little"), 4)

    def test_optional_wechat_ui_dependency_is_not_duplicated(self):
        core = (ROOT / "requirements.txt").read_text("utf-8")
        optional = (ROOT / "requirements-wechat-ui.txt").read_text("utf-8")

        self.assertNotIn("pywechat127", core)
        self.assertIn("pywechat127==1.9.8", optional)

    def test_launcher_starts_hidden_and_waits_for_health(self):
        launcher = (ROOT / "launch.ps1").read_text("utf-8")

        self.assertIn("/api/health", launcher)
        self.assertIn("-WindowStyle Hidden", launcher)
        self.assertIn("Start-Process", launcher)
        self.assertIn("Medical Knowledge Hub failed to start", launcher)

    def test_readme_has_a_clean_machine_reproduction_guide(self):
        readme = (ROOT / "README.md").read_text("utf-8")

        for section in ("## 五分钟复现", "## 验收清单", "## 故障排查"):
            self.assertIn(section, readme)
        for dependency in ("GitHub CLI", "Codex CLI", "OpenCLI", "OBSIDIAN_VAULT_PATH"):
            self.assertIn(dependency, readme)

    def test_application_reports_the_release_version(self):
        app_source = (ROOT / "app.py").read_text("utf-8")
        self.assertIn('APP_VERSION = "1.2.0"', app_source)
        self.assertIn("version=APP_VERSION", app_source)

    def test_daily_worker_purges_expired_recycle_bin_items(self):
        worker = (ROOT / "extensions/subscriptions/worker.py").read_text("utf-8")

        self.assertIn("purge_expired_trash", worker)


if __name__ == "__main__":
    unittest.main()
