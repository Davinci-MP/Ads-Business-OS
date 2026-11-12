"""CDP bootstrap regression tests: no real browser or Facebook requests."""
import json
from unittest.mock import Mock

import pytest

from app.services import chrome_launcher as launcher


@pytest.mark.parametrize("cookie,expected", [
    ("", False),
    ("c_user=123; xs=mock_xs_test", False),
    ("c_user=123; xs=34%3Atest_fixture_session_123456789", True),
])
def test_cookies_loaded_before_navigation(tmp_path, monkeypatch, cookie, expected):
    (tmp_path / "DevToolsActivePort").write_text("12345\n/devtools/browser/test\n")
    sent = []
    ws = Mock()
    ws.send.side_effect = lambda payload: sent.append(json.loads(payload))

    def receive(**kwargs):
        message = sent[-1]
        result = {"Target.createTarget": {"targetId": "tab"},
                  "Target.attachToTarget": {"sessionId": "session"}}.get(message["method"], {})
        return json.dumps({"id": message["id"], "result": result})

    ws.recv.side_effect = receive
    connection = Mock(return_value=ws)
    monkeypatch.setattr(launcher, "connect", connection)
    monkeypatch.setattr(launcher.threading, "Thread", Mock())
    launcher.initialize_browser_session(tmp_path, cookie, "https://www.facebook.com/login.php", "// helper")
    methods = [m["method"] for m in sent]
    assert ("Storage.setCookies" in methods) is expected
    if expected:
        assert methods.index("Storage.setCookies") < methods.index("Page.navigate")
    assert methods.index("Page.addScriptToEvaluateOnNewDocument") < methods.index("Page.navigate")
    assert sent[-1]["params"]["url"] == "https://www.facebook.com/login.php"
    assert connection.call_args.args[0].startswith("ws://127.0.0.1:")


def test_cdp_error_is_not_reported_as_success(tmp_path, monkeypatch):
    (tmp_path / "DevToolsActivePort").write_text("12345\n/devtools/browser/test\n")
    ws = Mock()
    ws.recv.return_value = json.dumps({"id": 1, "error": {"message": "fixture"}})
    monkeypatch.setattr(launcher, "connect", Mock(return_value=ws))
    with pytest.raises(RuntimeError):
        launcher.initialize_browser_session(tmp_path, "", "https://www.facebook.com/login.php", "")
    ws.close.assert_called_once()
