"""Flask web app — UI quản lý affiliate scraper.

Chạy: python web/app.py → http://localhost:5000
"""
from __future__ import annotations
import sys
import sqlite3
import subprocess
import threading
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import json as _json
from flask import Flask, render_template, jsonify, request, redirect, url_for
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "data" / "metrics.db"
USERS_PATH = ROOT / "config" / "users.json"

app = Flask(__name__)
auth = HTTPBasicAuth()

# Load users → hash password
_USERS_HASH = {}
if USERS_PATH.exists():
    _cfg = _json.loads(USERS_PATH.read_text(encoding="utf-8"))
    for u, p in _cfg.get("users", {}).items():
        _USERS_HASH[u] = generate_password_hash(p)


@auth.verify_password
def verify_password(username, password):
    h = _USERS_HASH.get(username)
    if h and check_password_hash(h, password):
        return username
    return None

# Theme per platform (gradient colors giống brolink)
PLATFORM_META = {
    "getrewardful":  {"name": "Rewardful",      "gradient": "from-emerald-500 to-teal-700",  "icon": "🟢", "status": "active"},
    "firstpromoter": {"name": "FirstPromoter",  "gradient": "from-pink-500 to-rose-700",     "icon": "🌸", "status": "active"},
    "tolt":          {"name": "Tolt",           "gradient": "from-blue-500 to-indigo-700",   "icon": "🔵", "status": "coming"},
    "goaffpro":      {"name": "GoAffPro",       "gradient": "from-green-500 to-emerald-700", "icon": "🟩", "status": "active"},
    "uppromote":     {"name": "UpPromote",      "gradient": "from-orange-500 to-amber-700",  "icon": "🟧", "status": "coming"},
    "impact":        {"name": "Impact",         "gradient": "from-cyan-500 to-blue-700",     "icon": "🔷", "status": "coming"},
    "partnerstack":  {"name": "PartnerStack",   "gradient": "from-violet-500 to-purple-700", "icon": "🟣", "status": "coming"},
    "dub":           {"name": "Dub.co",         "gradient": "from-slate-500 to-gray-700",    "icon": "⬛", "status": "coming"},
    "reditus":       {"name": "Reditus",        "gradient": "from-fuchsia-500 to-pink-700",  "icon": "🟪", "status": "coming"},
    "tapfiliate":    {"name": "Tapfiliate",     "gradient": "from-yellow-500 to-orange-600", "icon": "🟨", "status": "coming"},
    "trackdesk":     {"name": "Trackdesk",      "gradient": "from-red-500 to-rose-600",      "icon": "🟥", "status": "coming"},
    "refersion":     {"name": "Refersion",      "gradient": "from-lime-500 to-green-600",    "icon": "🟢", "status": "coming"},
    "promotekit":    {"name": "PromoteKit",     "gradient": "from-sky-500 to-blue-600",      "icon": "💙", "status": "coming"},
}


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def get_latest_date() -> str:
    with _conn() as c:
        row = c.execute("SELECT MAX(metric_date) AS d FROM daily_metrics").fetchone()
        return (row["d"] if row else None) or (date.today() - timedelta(days=1)).isoformat()


def get_platform_summary(metric_date: str | None = None):
    if not metric_date:
        metric_date = get_latest_date()
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM daily_metrics WHERE metric_date = ?",
            (metric_date,),
        ).fetchall()

    by_plat = defaultdict(list)
    for r in rows:
        by_plat[r["platform"]].append(dict(r))

    summary = []
    for key, meta in PLATFORM_META.items():
        items = by_plat.get(key, [])
        success = sum(1 for r in items if not r["error"])
        fail = len(items) - success
        total_unpaid = sum((r["unpaid"] or 0) for r in items)
        total_due_now = sum((r["due_now"] or 0) for r in items)
        total_pending_amount = sum((r["pending_amount"] or 0) for r in items)
        total_clicks = sum((r["clicks"] or 0) for r in items)
        summary.append({
            "key": key,
            "name": meta["name"],
            "gradient": meta["gradient"],
            "icon": meta["icon"],
            "status": meta["status"],
            "total": len(items),
            "success": success,
            "fail": fail,
            "total_clicks": total_clicks,
            "total_unpaid": round(total_unpaid, 2),
            "total_due_now": round(total_due_now, 2),
            "total_pending_amount": round(total_pending_amount, 2),
        })
    return summary, metric_date


def get_platform_rows(platform: str, metric_date: str | None = None):
    if not metric_date:
        metric_date = get_latest_date()
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM daily_metrics WHERE platform = ? AND metric_date = ? ORDER BY label",
            (platform, metric_date),
        ).fetchall()
    return [dict(r) for r in rows], metric_date


def get_dates_available():
    with _conn() as c:
        rows = c.execute(
            "SELECT DISTINCT metric_date FROM daily_metrics ORDER BY metric_date DESC LIMIT 30"
        ).fetchall()
    return [r["metric_date"] for r in rows]


# ---- Routes ----
@app.route("/")
@auth.login_required
def index():
    metric_date = request.args.get("date") or get_latest_date()
    summary, metric_date = get_platform_summary(metric_date)

    # Aggregate KPIs
    total_dashboards = sum(s["total"] for s in summary)
    total_success = sum(s["success"] for s in summary)
    total_fail = sum(s["fail"] for s in summary)
    total_unpaid = sum(s["total_unpaid"] for s in summary)
    total_due_now = sum(s["total_due_now"] for s in summary)
    total_pending = sum(s["total_pending_amount"] for s in summary)

    return render_template(
        "index.html",
        summary=summary,
        metric_date=metric_date,
        dates_available=get_dates_available(),
        kpi={
            "dashboards": total_dashboards,
            "success": total_success,
            "fail": total_fail,
            "success_rate": round(100 * total_success / total_dashboards, 1) if total_dashboards else 0,
            "total_unpaid": round(total_unpaid, 2),
            "total_due_now": round(total_due_now, 2),
            "total_pending": round(total_pending, 2),
        },
    )


@app.route("/platform/<platform>")
@auth.login_required
def platform_detail(platform: str):
    metric_date = request.args.get("date") or get_latest_date()
    rows, metric_date = get_platform_rows(platform, metric_date)
    meta = PLATFORM_META.get(platform, {"name": platform, "gradient": "from-gray-500 to-gray-700", "icon": "❓"})
    return render_template(
        "platform.html",
        platform=platform,
        meta=meta,
        rows=rows,
        metric_date=metric_date,
        dates_available=get_dates_available(),
    )


@app.route("/scrape/<platform>", methods=["POST"])
@auth.login_required
def trigger_scrape(platform: str):
    """Fire-and-forget background scrape."""
    def run():
        subprocess.Popen(
            [sys.executable, "-X", "utf8", "-m", "core.runner",
             "--platform", platform, "--force"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"ok": True, "started": platform})


@app.route("/api/stats")
@auth.login_required
def api_stats():
    metric_date = request.args.get("date") or get_latest_date()
    summary, _ = get_platform_summary(metric_date)
    return jsonify({"date": metric_date, "summary": summary})


if __name__ == "__main__":
    import socket
    # Lấy LAN IP để in ra cho team
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        lan_ip = "<your-lan-ip>"
    print()
    print("=" * 60)
    print("  Affiliate Scraper Web App")
    print("=" * 60)
    print(f"  Local:    http://localhost:5000")
    print(f"  Network:  http://{lan_ip}:5000   ← chia sẻ link này cho team")
    print(f"  Users:    {', '.join(_USERS_HASH.keys())}")
    print("=" * 60)
    print()
    app.run(host="0.0.0.0", port=5000, debug=False)
