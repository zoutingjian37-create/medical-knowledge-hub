import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as app_module
from app import app


class LocalApiBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = TestClient(app)
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def test_untrusted_browser_origin_is_rejected(self):
        response = self.client.get(
            "/api/health", headers={"Origin": "https://evil.example"}
        )
        self.assertEqual(403, response.status_code)

    def test_untrusted_host_is_rejected(self):
        self.assertEqual(
            400,
            self.client.get("/api/health", headers={"Host": "evil.example"}).status_code,
        )

    def test_trusted_loopback_origin_remains_available(self):
        response = self.client.get(
            "/api/health", headers={"Origin": "http://127.0.0.1:5000"}
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            "http://127.0.0.1:5000",
            response.headers.get("access-control-allow-origin"),
        )

    def test_all_interface_bind_requires_explicit_opt_in(self):
        with patch.dict(
            os.environ, {"HOST": "0.0.0.0", "ALLOW_NETWORK_ACCESS": "0"}, clear=False
        ):
            self.assertEqual("127.0.0.1", app_module.resolve_bind_host())

    def test_local_env_file_is_loaded_without_overwriting_process_values(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "CONTENT_HUB_TEST_FROM_FILE=loaded\n"
                "CONTENT_HUB_TEST_PRESERVED=file-value\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"CONTENT_HUB_TEST_PRESERVED": "process-value"},
                clear=False,
            ):
                os.environ.pop("CONTENT_HUB_TEST_FROM_FILE", None)
                self.assertTrue(hasattr(app_module, "load_local_env"))

                app_module.load_local_env(env_file)

                self.assertEqual("loaded", os.environ["CONTENT_HUB_TEST_FROM_FILE"])
                self.assertEqual("process-value", os.environ["CONTENT_HUB_TEST_PRESERVED"])
                os.environ.pop("CONTENT_HUB_TEST_FROM_FILE", None)

if __name__ == "__main__":
    unittest.main()
