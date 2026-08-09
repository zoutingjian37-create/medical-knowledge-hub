import tempfile
import unittest
from pathlib import Path

from release_privacy_check import find_privacy_violations


class ReleasePrivacyCheckTests(unittest.TestCase):
    def test_placeholders_are_allowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "env.example").write_text("API_KEY=your-api-key-here\n", "utf-8")

            self.assertEqual((), find_privacy_violations(root))

    def test_runtime_state_and_realistic_secrets_are_rejected_without_echoing_value(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_key = "sk-proj-" + ("a" * 32)
            (root / "settings.py").write_text(
                f'api_key = "{fake_key}"\n',
                "utf-8",
            )
            (root / "state").mkdir()
            (root / "state" / "subscriptions.json").write_text("{}", "utf-8")

            violations = find_privacy_violations(root)

            self.assertTrue(any("settings.py" in item for item in violations))
            self.assertTrue(any("subscriptions.json" in item for item in violations))
            self.assertFalse(any(fake_key in item for item in violations))


if __name__ == "__main__":
    unittest.main()
