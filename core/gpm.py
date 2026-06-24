"""Client cho GPM Login Local API — hỗ trợ multi-profile theo email."""
from __future__ import annotations
import json
import time
import socket
import urllib.request
import urllib.error
from contextlib import contextmanager
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config" / "gpm.json"


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Thiếu {CONFIG_PATH}")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _request(method: str, url: str, body: dict | None = None, timeout: int = 30) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"success": False, "message": f"HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')}"}
    except Exception as e:
        return {"success": False, "message": f"{type(e).__name__}: {e}"}


class GPMClient:
    def __init__(self, host: str | None = None):
        cfg = _load_config()
        self.cfg = cfg
        self.host = host or cfg["host"]
        self.base = f"http://{self.host}"

    def resolve_profile(self, email: str | None = None) -> str:
        """Trả về profile_id ứng với email. Fallback default."""
        mapping = self.cfg.get("email_to_profile", {})
        if email and email in mapping:
            return mapping[email]
        if self.cfg.get("default_profile_id"):
            return self.cfg["default_profile_id"]
        if self.cfg.get("profile_id"):
            return self.cfg["profile_id"]
        raise ValueError(f"Không tìm thấy profile_id cho email '{email}' và ko có default")

    def start_profile(self, profile_id: str) -> dict:
        url = f"{self.base}/api/v3/profiles/start/{profile_id}"
        return _request("GET", url, timeout=60)

    def close_profile(self, profile_id: str) -> dict:
        url = f"{self.base}/api/v3/profiles/close/{profile_id}"
        return _request("GET", url, timeout=30)


def _wait_cdp_ready(cdp_addr: str, timeout: int = 30):
    host, port = cdp_addr.split(":")
    port = int(port)
    for _ in range(timeout):
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"CDP port {cdp_addr} không mở sau {timeout}s")


@contextmanager
def open_profile(profile_id: str | None = None, email: str | None = None, close_when_done: bool = True):
    """Mở profile GPM, trả về (browser, page).

    Truyền `email` để auto-resolve profile_id từ mapping email→profile.
    Hoặc truyền `profile_id` trực tiếp.
    """
    from playwright.sync_api import sync_playwright

    client = GPMClient()
    pid = profile_id or client.resolve_profile(email=email)

    resp = client.start_profile(pid)
    if not resp.get("success"):
        raise RuntimeError(f"GPM start profile {pid} thất bại: {resp.get('message')}")

    cdp_addr = resp["data"]["remote_debugging_address"]
    cdp_url = f"http://{cdp_addr}"
    _wait_cdp_ready(cdp_addr)
    time.sleep(1)

    playwright_ctx = sync_playwright().start()
    browser = None
    try:
        browser = playwright_ctx.chromium.connect_over_cdp(cdp_url)
        if not browser.contexts:
            raise RuntimeError("Browser không có context — GPM profile lạ")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        yield browser, page
    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            playwright_ctx.stop()
        except Exception:
            pass
        if close_when_done:
            client.close_profile(pid)
