import json
import subprocess
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import HTTPServer
from threading import Thread

from mac_ai_bridge.automation import BridgeError, ask
from mac_ai_bridge.server import BridgeHandler


class AutomationTests(unittest.TestCase):
    @patch("mac_ai_bridge.automation.Path.is_file", return_value=True)
    @patch("mac_ai_bridge.automation.Path.is_dir", return_value=True)
    @patch("mac_ai_bridge.automation.subprocess.run")
    def test_ask_opens_allowlisted_app_and_returns_reply(self, run, _is_dir, _is_file):
        run.side_effect = [
            None,
            type("Completed", (), {"stdout": "A reply\n", "stderr": ""})(),
        ]
        self.assertEqual(ask("gemini", "Hello"), "A reply")
        self.assertEqual(run.call_count, 2)
        self.assertIn("swift", run.call_args.args[0][0])
        self.assertIn("com.google.GeminiMacOS", run.call_args.args[0])
        self.assertIn("Hello", run.call_args.args[0])

    def test_rejects_unknown_app_before_launching(self):
        with self.assertRaisesRegex(BridgeError, "Unsupported app"):
            ask("browser", "Hello")

    def test_rejects_empty_prompt(self):
        with self.assertRaisesRegex(BridgeError, "non-empty"):
            ask("copilot", "  ")

    @patch("mac_ai_bridge.automation.Path.is_file", return_value=True)
    @patch("mac_ai_bridge.automation.Path.is_dir", return_value=True)
    @patch("mac_ai_bridge.automation.subprocess.run")
    def test_native_helper_errors_are_reported(self, run, _is_dir, _is_file):
        run.side_effect = [
            None,
            subprocess.CalledProcessError(
                1, ["swift"], stderr="macOS blocked keyboard/mouse control"
            ),
        ]
        with self.assertRaisesRegex(BridgeError, "macOS blocked keyboard/mouse control"):
            ask("vscode", "Hello")


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), BridgeHandler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    @patch("mac_ai_bridge.server.ask", return_value="sample response")
    def test_post_ask_returns_plain_text(self, ask_mock):
        body = json.dumps({"app": "gemini", "prompt": "Hello"}).encode()
        request = Request(
            f"{self.url}/ask",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            self.assertEqual(response.headers.get_content_type(), "text/plain")
            self.assertEqual(response.read().decode(), "sample response")
        ask_mock.assert_called_once_with("gemini", "Hello")

    def test_post_ask_rejects_unknown_app(self):
        body = json.dumps({"app": "other", "prompt": "Hello"}).encode()
        request = Request(
            f"{self.url}/ask",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request)
        self.assertEqual(raised.exception.code, 400)

    def test_health_lists_available_apps(self):
        with urlopen(f"{self.url}/health") as response:
            data = json.loads(response.read())
        self.assertEqual(data["apps"], ["copilot", "gemini", "vscode"])

    @patch("mac_ai_bridge.server.ask", side_effect=BridgeError("Accessibility permission is required"))
    def test_post_ask_reports_ui_permission_errors(self, _ask_mock):
        body = json.dumps({"app": "vscode", "prompt": "Hello"}).encode()
        request = Request(
            f"{self.url}/ask",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request)
        self.assertEqual(raised.exception.code, 502)
        self.assertEqual(
            json.loads(raised.exception.read()),
            {"error": "Accessibility permission is required"},
        )


if __name__ == "__main__":
    unittest.main()
