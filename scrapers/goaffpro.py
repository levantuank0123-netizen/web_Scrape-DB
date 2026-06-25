"""GoAffPro affiliate scraper — HTTP API thuần (KHÔNG GPM/browser).

Mỗi brand = 1 shop riêng ở {brand}.goaffpro.com, dùng chung API api.goaffpro.com.
Flow:
  1. POST /partner/login  body {email, password, partner_portal_subdomain}  → JWT
  2. GET  /partner/payments          → tiền (earned/pending/paid/payable)
  3. GET  /partner/analytics/visits  → clicks (visits) + orders (sales.num_orders)
  4. GET  /partner/sales             → ref_count (số bản ghi sale)
  5. GET  /partner/                  → currency + referral_link

Login dùng `requests`, không cần recaptcha. Token JWT trả thẳng trong response.
"""
from __future__ import annotations
import json
from datetime import date
from urllib.parse import urlparse

import requests

from scrapers._http_base import HttpScraper

API = "https://api.goaffpro.com"


def _num(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class GoAffProScraper(HttpScraper):
    PLATFORM = "goaffpro"

    def fetch(self, metric_date: date) -> dict:
        sub = urlparse(self.account["dashboard_url"]).netloc
        origin = f"https://{sub}"
        s = requests.Session()
        s.headers.update({
            "user-agent": "Mozilla/5.0",
            "accept": "application/json",
            "content-type": "application/json",
            "origin": origin,
            "referer": origin + "/",
        })

        # ---- 1. Login ----
        try:
            r = s.post(f"{API}/partner/login", data=json.dumps({
                "email": self.account.get("email", ""),
                "password": str(self.account.get("password", "")),
                "partner_portal_subdomain": sub,
                "recaptcha_response": None,
            }), timeout=30)
        except requests.RequestException as e:
            return self._record(metric_date, error=f"Lỗi kết nối: {e}")

        if r.status_code >= 500:
            return self._record(metric_date, error=f"Lỗi kết nối: GoAffPro {r.status_code}")
        try:
            lj = r.json()
        except ValueError:
            return self._record(metric_date, error=f"Lỗi kết nối: login non-JSON {r.status_code}")

        token = lj.get("access_token")
        if not token:
            code = (lj.get("code") or "").upper()
            if lj.get("require_recaptcha"):
                return self._record(metric_date, error="Có Captcha — cần login thủ công")
            if code in ("USERDOESNOTEXISTS", "USEREXISTS", "INCORRECTPASSWORD", "EMAILINVALID"):
                return self._record(metric_date, error="TK bị Xóa Dashboard")
            return self._record(metric_date, error=f"Login fail: {lj.get('error') or code or r.status_code}")

        s.headers["authorization"] = f"Bearer {token}"

        rec = self._record(metric_date, currency="USD")
        raw = {}

        def _get(path):
            try:
                resp = s.get(f"{API}{path}", timeout=30)
                if resp.status_code == 200:
                    return resp.json()
            except (requests.RequestException, ValueError):
                pass
            return None

        # ---- 2. Payments (tiền) ----
        pay = _get("/partner/payments")
        if isinstance(pay, dict):
            raw["payments"] = pay
            rec["total_earned"] = _num(pay.get("amount_earned"))
            rec["unpaid"] = _num(pay.get("amount_pending"))
            rec["paid"] = _num(pay.get("amount_paid"))
            rec["due_now"] = _num(pay.get("amount_payable"))

        # ---- 3. Traffic sources → clicks (sum visits) ----
        # (endpoint /analytics/visits luôn trả rỗng; traffic_sources mới có data)
        traffic = _get("/partner/analytics/traffic_sources")
        if isinstance(traffic, dict) and isinstance(traffic.get("traffic"), list):
            rec["clicks"] = sum(int(t.get("visits") or 0) for t in traffic["traffic"])

        # ---- 4. Sales list → orders + ref_count (số đơn referral) ----
        sales_list = _get("/partner/sales")
        if isinstance(sales_list, dict) and sales_list.get("total") is not None:
            n = int(sales_list.get("total") or 0)
            rec["orders"] = n
            rec["ref_count"] = n

        # ---- 5. Config → currency + referral_link ----
        cfg = _get("/partner/")
        if isinstance(cfg, dict):
            st = cfg.get("settings") or {}
            if st.get("default_currency"):
                rec["currency"] = st["default_currency"]
            link = st.get("referral_link")
            if link and "ref=undefined" not in link:
                rec["ref_link"] = link

        rec["raw_json"] = raw
        return rec
