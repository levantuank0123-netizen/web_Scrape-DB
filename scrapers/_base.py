"""Base class cho scraper (GPM mode + login fallback).

Lưu ý: Profile GPM nên login sẵn để khỏi login lại. Nhưng nếu chưa login,
adapter có thể override `login()` để tự login bằng email/password trong Excel.
"""
from __future__ import annotations
from datetime import date, timedelta
from playwright.sync_api import Page


class BaseScraper:
    PLATFORM: str = ""
    DASHBOARD_URL: str = ""
    LOGIN_URL_PATTERNS = ("login", "signin", "sign-in", "sign_in")

    def __init__(self, account: dict):
        self.account = account
        self.label = account["label"]

    def run(self, page: Page, metric_date: date | None = None) -> dict:
        if metric_date is None:
            metric_date = date.today() - timedelta(days=1)

        dashboard = self.account.get("dashboard_url") or self.DASHBOARD_URL
        if not dashboard:
            raise ValueError(f"[{self.PLATFORM}/{self.label}] Thiếu dashboard_url")

        # Retry vòng ngoài: nếu extract trả về không data + không banned → goto lại + chờ lâu hơn
        MAX_ATTEMPTS = 3
        last_result = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                last_result = self._run_once(page, dashboard, metric_date, attempt)
            except Exception as e:
                last_result = self._err(metric_date, f"{type(e).__name__}: {e}")
            # Đã có data hoặc error rõ → return
            if last_result.get("error") or self._has_data(last_result):
                return last_result
            # Không data + không error → retry
            print(f"  ⚠ Lần {attempt} không có data + không có error rõ ràng, chờ {10*attempt}s rồi retry...")
            page.wait_for_timeout(10000 * attempt)
        # Hết retry → mark transient
        if last_result and not last_result.get("error"):
            last_result["error"] = "Login fail / page load chậm (3 lần đều fail)"
        return last_result or self._err(metric_date, "Login fail / page load chậm")

    def _has_data(self, result: dict) -> bool:
        """Có ít nhất 1 trường data → coi như scrape thành công."""
        fields = ["ref_link", "ref_count", "clicks", "impressions", "orders",
                  "total_earned", "unpaid", "due_now", "paid",
                  "pending_count", "pending_amount"]
        return any(result.get(f) is not None for f in fields)

    def _run_once(self, page: Page, dashboard: str, metric_date: date, attempt: int) -> dict:
        print(f"  → goto {dashboard} (lần {attempt})")
        try:
            page.goto(dashboard, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  goto thất bại: {e}, thử lại sau 5s...")
            page.wait_for_timeout(5000)
            page.goto(dashboard, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000 + attempt * 2000)  # chờ lâu hơn ở các lần sau

        # Detect 429 → retry liên tục trong 30s budget, mỗi lần wait 5s
        import time as _t
        import re as _re
        deadline = _t.time() + 30
        retry_count = 0
        is_429 = False
        while _t.time() < deadline:
            try:
                body_preview = page.inner_text("body")[:500]
            except Exception:
                body_preview = ""
            if not _re.search(r"429.*too\s*many\s*requests|too\s*many\s*requests",
                              body_preview, _re.IGNORECASE | _re.DOTALL):
                is_429 = False
                break
            is_429 = True
            retry_count += 1
            print(f"  ⚠ 429 rate limit (lần {retry_count}) → wait 5s + retry...")
            _t.sleep(5)
            try:
                page.goto(dashboard, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"  retry goto lỗi: {e}")
        if is_429:
            # Hết 30s vẫn 429 → trả về error TRANSIENT, sẽ retry lần sau
            print(f"  ⚠ 30s vẫn 429, bỏ qua (sẽ retry lần sau)")
            return self._err(metric_date, "Lỗi kết nối")

        if self._is_on_login(page):
            if self.account.get("email") and self.account.get("password"):
                print(f"  Phát hiện trang login → auto-login...")
                self.login(page, self.account)
                page.wait_for_timeout(2000)

                # Check immediately for "Invalid email/password" error text — confirmed bad creds
                try:
                    body_after_login = page.inner_text("body")[:1500]
                except Exception:
                    body_after_login = ""
                import re as _re
                if _re.search(
                    r"invalid\s+(email|password|credential|login)|"
                    r"wrong\s+(email|password|credential)|"
                    r"incorrect\s+(email|password|credential)|"
                    r"sai\s+(m[ậa]t\s+kh[ẩâ]u|email|t[àa]i\s+kho[ạa]n)",
                    body_after_login, _re.IGNORECASE):
                    return self._err(metric_date, "TK bị Xóa Dashboard")

                page.goto(dashboard, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)
                url_after = page.url.lower()
                still_on_login = (
                    any(p in url_after for p in self.LOGIN_URL_PATTERNS)
                    and bool(page.query_selector('input[type="password"]:visible'))
                )
                if still_on_login:
                    return self._err(metric_date, "TK bị Xóa Dashboard")
            else:
                return self._err(metric_date, "Profile chưa login dashboard này, mà Excel ko có email/password để auto-login")

        metrics = self.extract_metrics(page, self.account, metric_date)
        # Sanity check ĐÃ chuyển vào outer run() — _run_once chỉ trả về metrics raw,
        # outer sẽ retry nếu không có data + không có error.
        return {
            "platform": self.PLATFORM,
            "label": self.label,
            "owner": self.account.get("owner", ""),
            "email": self.account.get("email", ""),
            "login_url": self.account.get("dashboard_url", ""),
            "metric_date": metric_date.isoformat(),
            **metrics,
        }

    def _is_on_login(self, page: Page) -> bool:
        """Detect login page: URL có 'login'/'signin' VÀ có form password visible.
        Tránh false positive khi dashboard có chứa từ 'login' trong URL hoặc input password ẩn."""
        url = page.url.lower()
        url_match = any(p in url for p in self.LOGIN_URL_PATTERNS)
        try:
            has_pwd = bool(page.query_selector('input[type="password"]:visible'))
        except Exception:
            has_pwd = False
        # Trang login THẬT khi URL match hoặc thấy form password
        return url_match or has_pwd

    def _err(self, metric_date: date, msg: str) -> dict:
        return {
            "platform": self.PLATFORM,
            "label": self.label,
            "owner": self.account.get("owner", ""),
            "email": self.account.get("email", ""),
            "login_url": self.account.get("dashboard_url", ""),
            "metric_date": metric_date.isoformat(),
            "error": msg,
        }

    # ---- Override ----
    def login(self, page: Page, account: dict):
        """Mặc định: điền email + password + submit. Override nếu platform có flow khác."""
        email_sel = 'input[type="email"]:visible, input[name="email"]:visible, input[autocomplete="email"]:visible'
        pwd_sel = 'input[type="password"]:visible, input[name="password"]:visible'
        submit_sel = (
            'button[type="submit"]:visible, input[type="submit"]:visible, '
            'button:has-text("Log in"), button:has-text("Login"), '
            'button:has-text("Sign in"), button:has-text("Continue")'
        )
        page.wait_for_selector(email_sel, timeout=15000)
        page.fill(email_sel, account["email"])
        page.fill(pwd_sel, account["password"])
        page.click(submit_sel)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

    def extract_metrics(self, page: Page, account: dict, metric_date: date) -> dict:
        raise NotImplementedError
