"""Base cho scraper kiểu HTTP-API (KHÔNG cần browser/GPM).

Nhiều platform affiliate là SPA gọi REST API trả JSON. Thay vì mở browser,
ta login + gọi API trực tiếp bằng `requests` → nhanh, chính xác (JSON gốc),
không phụ thuộc GPM/proxy/profile.

Mỗi adapter override `fetch()` trả về record có cùng schema với scraper GPM
(để dùng chung core.db.save_metric + sheet_sync).
"""
from __future__ import annotations
from datetime import date, timedelta


class HttpScraper:
    PLATFORM: str = ""

    def __init__(self, account: dict):
        self.account = account
        self.label = account["label"]

    # ---- API công khai ----
    def run(self, metric_date: date | None = None) -> dict:
        if metric_date is None:
            metric_date = date.today() - timedelta(days=1)
        try:
            return self.fetch(metric_date)
        except Exception as e:
            return self._record(metric_date, error=f"{type(e).__name__}: {e}")

    # ---- Helper tạo record đúng schema ----
    def _record(self, metric_date: date, **fields) -> dict:
        rec = {
            "platform": self.PLATFORM,
            "label": self.label,
            "owner": self.account.get("owner", ""),
            "email": self.account.get("email", ""),
            "login_url": self.account.get("dashboard_url", ""),
            "metric_date": metric_date.isoformat() if isinstance(metric_date, date) else metric_date,
            "ref_link": None, "ref_count": None, "clicks": None, "impressions": None,
            "orders": None, "total_earned": None, "unpaid": None, "due_now": None,
            "paid": None, "pending_count": None, "pending_amount": None,
            "currency": None, "raw_json": None, "error": None,
        }
        rec.update(fields)
        return rec

    # ---- Override ----
    def fetch(self, metric_date: date) -> dict:
        raise NotImplementedError
