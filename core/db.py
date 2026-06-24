"""SQLite storage cho metrics theo ngày."""
import sqlite3
import json
from pathlib import Path
from datetime import date

DB_PATH = Path(__file__).parent.parent / "data" / "metrics.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    label TEXT NOT NULL,
    owner TEXT,
    email TEXT,
    metric_date TEXT NOT NULL,
    ref_link TEXT,
    ref_count INTEGER,
    clicks INTEGER,
    impressions INTEGER,
    orders INTEGER,
    total_earned REAL,
    unpaid REAL,
    due_now REAL,
    paid REAL,
    pending_count INTEGER,
    pending_amount REAL,
    currency TEXT,
    raw_json TEXT,
    scraped_at TEXT NOT NULL,
    error TEXT,
    error_permanent INTEGER DEFAULT 0,
    UNIQUE(platform, label, metric_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_metrics(metric_date);
CREATE INDEX IF NOT EXISTS idx_daily_platform ON daily_metrics(platform);
"""


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(SCHEMA)
    return conn


def save_metric(record: dict):
    """Upsert 1 row metric. record = dict có các key map vào schema."""
    from datetime import datetime
    record = {**record}
    record["scraped_at"] = datetime.utcnow().isoformat()
    if isinstance(record.get("raw_json"), (dict, list)):
        record["raw_json"] = json.dumps(record["raw_json"], ensure_ascii=False)
    if isinstance(record.get("metric_date"), date):
        record["metric_date"] = record["metric_date"].isoformat()

    cols = [
        "platform", "label", "owner", "email", "metric_date", "ref_link", "ref_count",
        "clicks", "impressions", "orders",
        "total_earned", "unpaid", "due_now", "paid",
        "pending_count", "pending_amount",
        "currency", "raw_json", "scraped_at", "error",
        "error_permanent",
    ]
    values = [record.get(c) for c in cols]
    placeholders = ",".join("?" * len(cols))
    update_clause = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("platform", "label", "metric_date"))

    with get_conn() as conn:
        conn.execute(
            f"INSERT INTO daily_metrics ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(platform, label, metric_date) DO UPDATE SET {update_clause}",
            values,
        )


def fetch_metrics(metric_date: str | None = None):
    """Trả về list dict metrics. Nếu metric_date=None thì lấy tất cả."""
    with get_conn() as conn:
        if metric_date:
            rows = conn.execute(
                "SELECT * FROM daily_metrics WHERE metric_date = ? ORDER BY platform, label",
                (metric_date,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM daily_metrics ORDER BY metric_date DESC, platform, label"
            ).fetchall()
    return [dict(r) for r in rows]


def get_done_set(metric_date: str) -> set[tuple[str, str]]:
    """Trả về set (platform, label) coi như 'xong' cho ngày này.

    Bao gồm:
      - rows không có lỗi (scrape thành công)
      - rows có lỗi PERMANENT (TK bị xóa, captcha, dashboard ko tồn tại, ...)

    Rows có lỗi TRANSIENT (lỗi kết nối, lỗi unknown) sẽ KHÔNG nằm trong done → retry.
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT platform, label FROM daily_metrics "
            "WHERE metric_date = ? AND ("
            "  (error IS NULL OR error = '') OR error_permanent = 1"
            ")",
            (metric_date,),
        ).fetchall()
    return {(r["platform"], r["label"]) for r in rows}
