"""FirstPromoter (firstpromoter.com) affiliate dashboard scraper.

Mỗi brand 1 subdomain: {brand}.firstpromoter.com
Dashboard chính ở /home, gồm:
  - 3 thẻ top: DUE IN 6 DAYS | TOTAL UNPAID | TOTAL PAID
  - Card chương trình: Clicks | Referrals | Customers
  - Status badge (Pending/Blocked/Active)
"""
from __future__ import annotations
import re
from datetime import date
from urllib.parse import urlparse
from playwright.sync_api import Page
from scrapers._base import BaseScraper


def _parse_number(s):
    if not s: return None
    s = re.sub(r"[^\d\.,\-]", "", str(s).strip())
    if not s: return None
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


def _parse_int(s):
    v = _parse_number(s)
    return int(v) if v is not None else None


class FirstPromoterScraper(BaseScraper):
    PLATFORM = "firstpromoter"
    DASHBOARD_URL = ""

    def _normalize_url(self, url: str) -> str:
        """FirstPromoter dashboard luôn ở root subdomain hoặc /home."""
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}/home"

    def run(self, page, metric_date=None):
        original = self.account.get("dashboard_url", "")
        if original:
            self.account = {**self.account, "dashboard_url": self._normalize_url(original)}
        return super().run(page, metric_date=metric_date)

    def login(self, page: Page, account: dict):
        """Login form đơn giản: email + password + Sign In button."""
        p = urlparse(account.get("dashboard_url") or "")
        login_url = f"{p.scheme}://{p.netloc}/login"
        print(f"  → goto login: {login_url}")
        page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(2000)

        email_sel = 'input[type="email"]:visible, input[name="email"]:visible'
        pwd_sel = 'input[type="password"]:visible, input[name="password"]:visible'
        page.wait_for_selector(email_sel, timeout=15000)
        page.fill(email_sel, account["email"])
        page.fill(pwd_sel, account["password"])

        # Submit (button có text "Sign In")
        submit_sel = (
            'button:has-text("Sign In"), button:has-text("Sign in"), '
            'button:has-text("Log in"), button[type="submit"]'
        )
        page.click(submit_sel)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

    def extract_metrics(self, page: Page, account: dict, metric_date: date) -> dict:
        try:
            page.screenshot(path=f"logs/firstpromoter_{self.label}.png", full_page=True)
        except Exception:
            pass

        result = {
            "ref_link": None, "ref_count": None, "clicks": None,
            "impressions": None, "orders": None,
            "total_earned": None, "unpaid": None, "due_now": None, "paid": None,
            "pending_count": None, "pending_amount": None,
            "currency": None, "raw_json": None, "error": None,
        }

        try:
            body_text = page.inner_text("body")
        except Exception:
            body_text = ""

        # ---- Money: 3 cards ----
        # Pattern: "DUE IN 6 DAYS\n$0" hoặc "DUE IN 6 DAYS\n$27.5"
        # FirstPromoter dùng "DUE IN X DAYS" với X là số ngày
        m = re.search(r"DUE\s+IN\s+\d+\s+DAYS?\s*[\n\s]*([\$€£¥₫])\s*([\d.,]+)", body_text, re.IGNORECASE)
        if m:
            result["currency"] = m.group(1)
            result["due_now"] = _parse_number(m.group(2))

        m = re.search(r"TOTAL\s+UNPAID\s*[\n\s]*([\$€£¥₫])\s*([\d.,]+)", body_text, re.IGNORECASE)
        if m:
            result["currency"] = result["currency"] or m.group(1)
            result["unpaid"] = _parse_number(m.group(2))

        m = re.search(r"TOTAL\s+PAID\s*[\n\s]*([\$€£¥₫])\s*([\d.,]+)", body_text, re.IGNORECASE)
        if m:
            result["currency"] = result["currency"] or m.group(1)
            result["paid"] = _parse_number(m.group(2))

        # total_earned = unpaid + paid
        if result["unpaid"] is not None or result["paid"] is not None:
            result["total_earned"] = (result["unpaid"] or 0) + (result["paid"] or 0)

        # ---- Số liệu: Clicks | Referrals | Customers ----
        # Layout: "507\nClicks\n25\nReferrals\n3\nCustomers"
        m = re.search(r"([\d,]+)\s*\n\s*Clicks", body_text, re.IGNORECASE)
        if m:
            result["clicks"] = _parse_int(m.group(1))
        m = re.search(r"([\d,]+)\s*\n\s*Referrals?", body_text, re.IGNORECASE)
        if m:
            result["ref_count"] = _parse_int(m.group(1))
        m = re.search(r"([\d,]+)\s*\n\s*Customers?", body_text, re.IGNORECASE)
        if m:
            result["orders"] = _parse_int(m.group(1))

        # ---- Ref link: từ DOM input hoặc body text ----
        # FirstPromoter dùng ?fpr= làm pattern
        try:
            for sel in [
                'input[readonly][value*="?fpr="]',
                'input[value*="?fpr="]',
                'input[readonly][value*="?via="]',
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

        if not result["ref_link"]:
            # URL có thể là `?fpr=xxx` HOẶC `?utm=...&fpr=xxx`
            # → tìm mọi URL, lọc cái chứa [?&](fpr|via|ref)=
            for cand in re.findall(r"https?://[^\s]+", body_text):
                # Cắt URL ở ký tự không hợp lệ (\t, \n đã loại bởi \s)
                cand = cand.rstrip(".,)]\"'")
                if re.search(r"[?&](fpr|via|ref)=", cand):
                    result["ref_link"] = cand
                    break

        # ---- Rate limit check (429) ----
        if re.search(r"429.*too\s*many\s*requests|too\s*many\s*requests.*429", body_text, re.IGNORECASE | re.DOTALL):
            result["error"] = "Lỗi kết nối (429 rate limit)"
            result["raw_json"] = {"body_text_excerpt": body_text[:4000], "page_url": page.url}
            return result

        # ---- Affiliate program disabled (brand tắt chương trình) ----
        if re.search(r"affiliate\s*[/\\]?\s*referral\s+program\s+is\s+disabled|program\s+is\s+disabled",
                     body_text, re.IGNORECASE):
            result["error"] = "AFF Program Disable"
            result["raw_json"] = {"body_text_excerpt": body_text[:4000], "page_url": page.url}
            return result

        # ---- Banned/blocked: cần BOTH "You are banned" AND data extracted (hoặc badge "Blocked") ----
        # Tránh false positive: chỉ mark khi rõ ràng có text "you are banned/blocked"
        is_banned = bool(re.search(r"\byou\s*are\s*(banned|blocked)\b", body_text, re.IGNORECASE))
        if is_banned:
            result["error"] = "TK bị Xóa Dashboard"

        # ---- Navigate /my-commissions để lấy pending count + amount ----
        try:
            p = urlparse(page.url)
            commissions_url = f"{p.scheme}://{p.netloc}/my-commissions"
            print(f"  → goto commissions: {commissions_url}")
            page.goto(commissions_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
            comm_text = page.inner_text("body")

            # Parse pending rows: "Pending\s*[\$€£¥₫]\s*([\d.,]+)"
            pending_amounts = re.findall(
                r"Pending\s*\n?\s*([\$€£¥₫])\s*(-?[\d.,]+)",
                comm_text,
                re.IGNORECASE,
            )
            if pending_amounts:
                result["pending_count"] = len(pending_amounts)
                total = sum(_parse_number(a[1]) or 0 for a in pending_amounts)
                result["pending_amount"] = round(total, 2)
                if not result["currency"]:
                    result["currency"] = pending_amounts[0][0]
        except Exception as e:
            print(f"  (skip commissions: {e})")

        result["raw_json"] = {"body_text_excerpt": body_text[:4000], "page_url": page.url}
        return result
