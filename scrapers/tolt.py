"""Tolt (tolt.io) affiliate dashboard scraper — GPM mode."""
from __future__ import annotations
import re
from datetime import date
from urllib.parse import urlparse
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


def _find_after(body: str, label: str) -> str | None:
    """Tìm số ngay sau label trong body text."""
    m = re.search(
        rf"{re.escape(label)}\s*[\n:$€£]?\s*([\d,\.]+)",
        body, re.IGNORECASE
    )
    return m.group(1) if m else None


def _find_money(body: str, *labels: str) -> tuple[str | None, float | None]:
    """Trả về (currency_symbol, amount) từ block label → $X.XX."""
    pattern = "(" + "|".join(re.escape(l) for l in labels) + r")\s*\n?\s*([\$€£])?\s*([\d,\.]+)"
    m = re.search(pattern, body, re.IGNORECASE)
    if m:
        return m.group(2) or "$", _parse_number(m.group(3))
    return None, None


class ToltScraper(BaseScraper):
    PLATFORM = "tolt"
    DASHBOARD_URL = "https://app.tolt.io/"

    def _normalize_url(self, url: str) -> str:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}/"

    def run(self, page: Page, metric_date=None):
        original = self.account.get("dashboard_url", "")
        if original:
            self.account = {**self.account, "dashboard_url": self._normalize_url(original)}
        return super().run(page, metric_date=metric_date)

    def extract_metrics(self, page: Page, account: dict, metric_date: date) -> dict:
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
            "currency": "USD",
            "raw_json": None,
            "error": None,
        }

        # Ref link
        try:
            link_input = page.query_selector(
                'input[readonly][value*="?ref="], input[readonly][value*="/ref/"], '
                'input[readonly][value*="?via="], input[readonly]'
            )
            if link_input:
                val = link_input.get_attribute("value")
                if val and ("ref=" in val or "via=" in val or len(val) > 10):
                    result["ref_link"] = val
        except Exception:
            pass

        try:
            body_text = page.inner_text("body")
        except Exception:
            body_text = ""

        result["raw_json"] = {"body_text_excerpt": body_text[:5000]}

        # --- Clicks ---
        result["clicks"] = _parse_int(_find_after(body_text, "Clicks") or
                                       _find_after(body_text, "Visitors") or
                                       _find_after(body_text, "Visits"))

        # --- Conversions / Referrals ---
        result["ref_count"] = _parse_int(_find_after(body_text, "Referrals") or
                                          _find_after(body_text, "Signups") or
                                          _find_after(body_text, "Sign ups") or
                                          _find_after(body_text, "Conversions"))

        result["orders"] = _parse_int(_find_after(body_text, "Orders") or
                                       _find_after(body_text, "Sales"))

        # --- Money fields ---
        # Tolt dashboard thường có: "Pending" (= unpaid), "Available" / "Balance" (= due_now), "Paid"
        cur, pending = _find_money(body_text, "Pending", "Unpaid")
        if cur:
            result["currency"] = cur
        result["unpaid"] = pending

        cur2, available = _find_money(body_text, "Available", "Balance", "Due", "Payout")
        if cur2 and not cur:
            result["currency"] = cur2
        result["due_now"] = available

        cur3, paid = _find_money(body_text, "Paid", "Total paid", "Withdrawn")
        result["paid"] = paid

        # Total earned = sum of all
        parts = [x for x in [pending, available, paid] if x is not None]
        if parts:
            result["total_earned"] = sum(parts)

        # Currency từ symbol $
        if not result["currency"]:
            m = re.search(r"([\$€£])\s*[\d,\.]+", body_text)
            if m:
                sym_map = {"$": "USD", "€": "EUR", "£": "GBP"}
                result["currency"] = sym_map.get(m.group(1), m.group(1))

        return result
