"""Rewardful affiliate dashboard scraper.

Mỗi brand có subdomain riêng: {brand}.getrewardful.com
Dashboard sau khi login hiển thị: referral link, visitors, leads, conversions,
commission earned, etc.
"""
from __future__ import annotations
import re
from datetime import date
from playwright.sync_api import Page
from scrapers._base import BaseScraper


def _parse_number(s: str | None) -> float | None:
    if not s:
        return None
    s = re.sub(r"[^\d\.,\-]", "", s.strip())
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        if re.search(r",\d{1,2}$", s):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_int(s: str | None) -> int | None:
    v = _parse_number(s)
    return int(v) if v is not None else None


class RewardfulScraper(BaseScraper):
    PLATFORM = "getrewardful"
    DASHBOARD_URL = ""  # bắt buộc Excel cung cấp (vì mỗi brand 1 subdomain)

    def _normalize_url(self, url: str) -> str:
        """Rewardful: dashboard luôn ở root subdomain. Bỏ path /profile, /login, ... vì có thể 404."""
        from urllib.parse import urlparse
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}/"

    def run(self, page, metric_date=None):
        # Normalize trước khi gọi flow chung
        original = self.account.get("dashboard_url", "")
        if original:
            self.account = {**self.account, "dashboard_url": self._normalize_url(original)}
        return super().run(page, metric_date=metric_date)

    def login(self, page: Page, account: dict):
        """Rewardful: trang gốc là signup → phải vào /login.

        Login luôn ở host_root + '/login', không phụ thuộc path dashboard_url.
        """
        from urllib.parse import urlparse
        base = account.get("dashboard_url") or ""
        p = urlparse(base)
        # Rewardful có 2 routes có thể chứa form login: /login và /affiliates/sign_in
        # Có brand redirect /login → / (signup). Thử nhiều URL.
        candidate_urls = [
            f"{p.scheme}://{p.netloc}/login",
            f"{p.scheme}://{p.netloc}/affiliates/sign_in",
            f"{p.scheme}://{p.netloc}/sign_in",
        ]
        email_sel = 'input[type="email"]:visible, input[name="email"]:visible, input[name="affiliate[email]"]:visible'
        pwd_sel = 'input[type="password"]:visible, input[name="password"]:visible, input[name="affiliate[password]"]:visible'

        form_found = False
        for url_try in candidate_urls:
            print(f"  → goto: {url_try}")
            try:
                page.goto(url_try, wait_until="domcontentloaded", timeout=45000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                page.wait_for_timeout(1500)
                # Có form login chưa?
                pwd = page.query_selector(pwd_sel)
                if pwd:
                    form_found = True
                    print(f"  ✓ tìm thấy form login tại {page.url}")
                    break
                print(f"  (không có form ở {page.url})")
            except Exception as e:
                print(f"  goto lỗi: {e}")

        if not form_found:
            try:
                page.screenshot(path=f"logs/no_form_{self.label}.png", full_page=True)
                body = page.inner_text("body")[:1500]
                print(f"  Body excerpt: {body[:500]!r}")
            except Exception:
                pass
            # Thử click "Sign in" / "Log in" / "Đăng nhập" link nếu có
            for txt in ["Sign in", "Log in", "Login", "Đăng nhập"]:
                try:
                    link = page.query_selector(f'a:has-text("{txt}")')
                    if link:
                        print(f"  → click link '{txt}'")
                        link.click()
                        page.wait_for_timeout(2500)
                        if page.query_selector(pwd_sel):
                            form_found = True
                            break
                except Exception:
                    pass
        if not form_found:
            raise RuntimeError("Không tìm thấy form login ở bất kỳ URL nào (/login, /affiliates/sign_in, /sign_in)")

        page.wait_for_selector(email_sel, timeout=15000)
        page.fill(email_sel, account["email"])
        page.fill(pwd_sel, account["password"])

        # Tick "Remember me" để giữ session lâu
        try:
            remember = page.query_selector(
                'input[type="checkbox"][name*="remember" i], '
                'input[type="checkbox"]#remember_me, '
                'input[type="checkbox"][name="affiliate[remember_me]"]'
            )
            if remember and not remember.is_checked():
                remember.check()
                print("  ✓ Tick Remember me")
        except Exception as e:
            print(f"  (skip remember me: {e})")

        # Rewardful dùng input[type=submit] hoặc button có text "Login"
        submit_sel = (
            'input[type="submit"][value*="Login" i], '
            'input[type="submit"][value*="Log in" i], '
            'input[type="submit"][value*="Sign in" i], '
            'button:has-text("Login"), button:has-text("Log in"), button:has-text("Sign in")'
        )
        page.click(submit_sel)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

    def extract_metrics(self, page: Page, account: dict, metric_date: date) -> dict:
        try:
            page.screenshot(path=f"logs/getrewardful_{self.label}.png", full_page=True)
        except Exception:
            pass

        result = {
            "ref_link": None,
            "ref_count": None,
            "clicks": None,
            "impressions": None,
            "orders": None,
            "total_earned": None,
            "unpaid": None,
            "due_now": None,
            "paid": None,
            "currency": None,
            "raw_json": None,
            "error": None,
        }

        try:
            body_text = page.inner_text("body")
        except Exception:
            body_text = ""

        # ---- Ref link ----
        # URL có thể `?via=xxx` HOẶC `?utm=...&via=xxx`
        for cand in re.findall(r"https?://[^\s]+", body_text):
            cand = cand.rstrip(".,)]\"'")
            if re.search(r"[?&](via|ref|fpr)=", cand):
                result["ref_link"] = cand
                break
        if not result["ref_link"]:
            try:
                for sel in [
                    'input[readonly][value*="?via="]',
                    'input[value*="?via="]',
                    'input[readonly][value*="?ref="]',
                ]:
                    el = page.query_selector(sel)
                    if el:
                        v = el.get_attribute("value")
                        if v:
                            result["ref_link"] = v
                            break
            except Exception:
                pass

        # ---- Bảng "Visitors | Leads | Conversions" → 3 số liền nhau ----
        m = re.search(
            r"Visitors\s*[\t\n ]+\s*Leads\s*[\t\n ]+\s*Conversions\s*[\t\n ]+\s*([\d,]+)\s*[\t\n ]+\s*([\d,]+)\s*[\t\n ]+\s*([\d,]+)",
            body_text,
            re.IGNORECASE,
        )
        if m:
            result["clicks"] = _parse_int(m.group(1))       # Visitors
            result["ref_count"] = _parse_int(m.group(2))    # Leads
            result["orders"] = _parse_int(m.group(3))       # Conversions

        # ---- Bảng "Unpaid | Paid | Total Earned" ----
        # Layout có 2 dạng:
        #   (A) không có due_now:  "Unpaid\tPaid\tTotal Earned\n$X USD\t$Y USD\t$Z USD"
        #   (B) có due_now:        "Unpaid\tPaid\tTotal Earned\n$X USD\n$D USD due now\n\t$Y USD\t$Z USD"
        # → tìm vị trí header, parse các money token ở sau, tách due_now nếu có
        header_m = re.search(r"Unpaid\s+Paid\s+Total\s+Earned", body_text, re.IGNORECASE)
        if header_m:
            after = body_text[header_m.end(): header_m.end() + 400]
            money_pat = r"([\$€£¥₫])\s*([\d.,]+)"
            tokens = re.findall(money_pat, after)
            due_m = re.search(rf"{money_pat}\s*\w*\s+due\s+now", after, re.IGNORECASE)
            if due_m:
                result["due_now"] = _parse_number(due_m.group(2))
                # 4 tokens: unpaid, due_now, paid, total_earned
                if len(tokens) >= 4:
                    result["currency"] = tokens[0][0]
                    result["unpaid"] = _parse_number(tokens[0][1])
                    result["paid"] = _parse_number(tokens[2][1])
                    result["total_earned"] = _parse_number(tokens[3][1])
            else:
                # 3 tokens: unpaid, paid, total_earned
                if len(tokens) >= 3:
                    result["currency"] = tokens[0][0]
                    result["unpaid"] = _parse_number(tokens[0][1])
                    result["paid"] = _parse_number(tokens[1][1])
                    result["total_earned"] = _parse_number(tokens[2][1])

        result["raw_json"] = {"body_text_excerpt": body_text[:4000], "page_url": page.url}
        return result
