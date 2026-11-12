"""Read-only browser QA against a local preview; never submits application forms."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "ui-refactor"
OUT.mkdir(parents=True, exist_ok=True)
PROFILE = OUT / "chrome-profile"
PROFILE.mkdir(exist_ok=True)
port_file = PROFILE / "DevToolsActivePort"
port_file.unlink(missing_ok=True)
chrome = subprocess.Popen([
    r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new",
    "--remote-debugging-port=0", f"--user-data-dir={PROFILE}", "--no-first-run",
    "--no-default-browser-check", "--disable-extensions", "about:blank",
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    for _ in range(100):
        if port_file.exists():
            break
        time.sleep(.1)
    port = port_file.read_text().splitlines()[0]
    tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5))
    target = next(tab for tab in tabs if tab.get("type") == "page")
    with connect(target["webSocketDebuggerUrl"], open_timeout=10, max_size=20_000_000) as ws:
        counter = 0
        errors = []
        def call(method, params=None):
            global counter
            counter += 1
            current = counter
            ws.send(json.dumps({"id": current, "method": method, "params": params or {}}))
            while True:
                reply = json.loads(ws.recv(timeout=30))
                if reply.get("method") == "Runtime.exceptionThrown":
                    errors.append(reply["params"]["exceptionDetails"].get("text", "Lỗi JavaScript"))
                if reply.get("id") == current:
                    if "error" in reply:
                        raise RuntimeError(reply["error"])
                    return reply.get("result", {})
        def evaluate(script):
            result = call("Runtime.evaluate", {"expression": script, "returnByValue": True})
            if "exceptionDetails" in result:
                raise RuntimeError(result["exceptionDetails"].get("text"))
            return result.get("result", {}).get("value")
        def size(width, height):
            call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 600})
        def screenshot(name):
            data = call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            (OUT / name).write_bytes(base64.b64decode(data["data"]))
        def navigate(path):
            call("Page.navigate", {"url": "http://127.0.0.1:3017" + path})
            for _ in range(80):
                time.sleep(.25)
                try:
                    if evaluate("location.pathname === " + json.dumps(path) + " && document.readyState === 'complete' && !!document.querySelector('main h1')"):
                        break
                except RuntimeError:
                    pass
            time.sleep(1)
        call("Page.enable")
        call("Runtime.enable")
        size(1440, 1050)
        navigate("/dashboard")
        evaluate("if(document.querySelector('.admin-shell').classList.contains('sidebar-is-collapsed'))document.querySelector('.collapse-button').click()")
        evaluate("localStorage.setItem('adsos.theme','dark'); window.dispatchEvent(new Event('adsos.preferences'))")
        time.sleep(.3)
        screenshot("dashboard-dark.png")
        evaluate("document.querySelector('button[aria-label=\"Bật giao diện sáng\"]').click()")
        time.sleep(.3)
        assert evaluate("document.documentElement.dataset.theme") == "light"
        screenshot("dashboard-light.png")
        checks = []
        for route in ["/dashboard", "/accounts", "/bms", "/vias", "/customers", "/analytics", "/auto-set-camp", "/settings"]:
            navigate(route)
            item = evaluate("({title: document.querySelector('main h1')?.textContent, width:innerWidth, scroll:document.documentElement.scrollWidth, main:!!document.querySelector('#main-content')})")
            item["route"] = route
            checks.append(item)
            assert item["main"] and item["title"], item
            assert item["scroll"] <= item["width"] + 1, item
        navigate("/customers")
        evaluate("[...document.querySelectorAll('main button')].find(b=>b.textContent.includes('Thêm khách hàng')).click()")
        time.sleep(.2)
        assert evaluate("!!document.querySelector('dialog[open]')")
        evaluate("document.querySelector('dialog button[aria-label]').click()")
        assert evaluate("!document.querySelector('dialog[open]')")
        navigate("/settings")
        evaluate("[...document.querySelectorAll('main button')].find(b=>b.textContent.includes('Giao diện')).click()")
        evaluate("[...document.querySelectorAll('main button')].find(b=>b.textContent.includes('Giao diện tối')).click()")
        time.sleep(.2)
        assert evaluate("document.documentElement.dataset.theme") == "dark"
        navigate("/accounts")
        evaluate("document.querySelector('select[aria-label=\"Số dòng mỗi trang\"]').value='10';document.querySelector('select[aria-label=\"Số dòng mỗi trang\"]').dispatchEvent(new Event('change',{bubbles:true}))")
        time.sleep(.3)
        assert evaluate("document.querySelectorAll('main tbody tr').length") <= 10
        size(1024, 900)
        for route in ["/dashboard", "/accounts", "/bms", "/vias", "/customers", "/analytics", "/auto-set-camp", "/settings"]:
            navigate(route)
            item = evaluate("({width:innerWidth, scroll:document.documentElement.scrollWidth})")
            item.update({"route": route, "tablet": True})
            checks.append(item)
            assert item["scroll"] <= item["width"] + 1, item
        navigate("/dashboard")
        evaluate("document.querySelector('.collapse-button').click()")
        time.sleep(.3)
        assert evaluate("document.querySelector('.admin-shell').classList.contains('sidebar-is-collapsed')")
        size(390, 844)
        for route in ["/dashboard", "/accounts", "/bms", "/vias", "/customers", "/analytics", "/auto-set-camp", "/settings"]:
            navigate(route)
            item = evaluate("({width:innerWidth, scroll:document.documentElement.scrollWidth})")
            item.update({"route": route, "mobile": True})
            checks.append(item)
            assert item["scroll"] <= item["width"] + 1, item
        navigate("/dashboard")
        screenshot("dashboard-mobile.png")
        evaluate("document.querySelector('button[aria-label=\"Mở điều hướng\"]').click()")
        time.sleep(.3)
        assert evaluate("document.querySelector('.admin-sidebar').classList.contains('mobile-open')")
        screenshot("mobile-navigation.png")
        evaluate("document.querySelector('.sidebar-backdrop').click()")
        assert not errors, errors
        (OUT / "browser-check.json").write_text(json.dumps({"checks": checks, "javascript_errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"passed": len(checks), "javascript_errors": errors, "screenshots": str(OUT)}, ensure_ascii=False))
finally:
    chrome.terminate()
    try:
        chrome.wait(timeout=10)
    except subprocess.TimeoutExpired:
        chrome.kill()
