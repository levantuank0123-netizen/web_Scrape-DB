"""Runner cho các platform kiểu HTTP-API (KHÔNG GPM/browser).

Chạy song song bằng thread (login + gọi API rất nhẹ). Lưu DB + đẩy Sheet
giống core/runner.py, dùng chung core.db + core.errors + sheet_sync.

Usage:
  python -m core.http_runner --all
  python -m core.http_runner --platform goaffpro
  python -m core.http_runner --platform goaffpro --limit 5 --no-sheet
  python -m core.http_runner --account arrtx --force
"""
from __future__ import annotations
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.accounts import load_accounts
from core.db import save_metric, get_done_set
from core.errors import classify as classify_error
from scrapers import HTTP_REGISTRY, get_http_scraper


def _finalize(record: dict) -> dict:
    if record.get("error"):
        msg, perm = classify_error(record["error"])
        record["error"] = msg
        record["error_permanent"] = 1 if perm else 0
    else:
        record["error"] = None
        record["error_permanent"] = 0
    return record


def _scrape_one(acc: dict, metric_date: date) -> dict:
    plat, label = acc["platform"], acc["label"]
    try:
        scraper = get_http_scraper(plat)(acc)
        rec = scraper.run(metric_date=metric_date)
    except Exception as e:
        rec = {
            "platform": plat, "label": label,
            "owner": acc.get("owner", ""), "email": acc.get("email", ""),
            "metric_date": metric_date.isoformat(),
            "error": f"{type(e).__name__}: {e}",
        }
    rec = _finalize(rec)
    save_metric(rec)
    return rec


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--platform")
    ap.add_argument("--account", help="Lọc theo label")
    ap.add_argument("--owner", help="Lọc theo người quản")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--date", help="YYYY-MM-DD, mặc định = hôm qua")
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--force", action="store_true", help="Chạy lại cả account đã có data")
    ap.add_argument("--max-workers", type=int, default=8)
    args = ap.parse_args()

    if not (args.all or args.platform or args.account or args.owner):
        ap.error("Phải chọn --all, --platform, --account hoặc --owner")

    metric_date = parse_date(args.date) if args.date else (date.today() - timedelta(days=1))

    accounts = load_accounts(
        only_active=True, label=args.account,
        platform=args.platform, owner=args.owner,
    )
    # chỉ giữ platform có HTTP adapter
    accounts = [a for a in accounts if a["platform"] in HTTP_REGISTRY]
    if not accounts:
        print(f"Không có account HTTP nào khớp. (HTTP platforms: {sorted(HTTP_REGISTRY)})")
        return 1

    if args.limit:
        accounts = accounts[: args.limit]

    if not args.force:
        done = get_done_set(metric_date.isoformat())
        before = len(accounts)
        accounts = [a for a in accounts if (a["platform"], a["label"]) not in done]
        skipped = before - len(accounts)
        if skipped:
            print(f"[skip] {skipped} account đã có data cho {metric_date}. Dùng --force để chạy lại.")
        if not accounts:
            print("Tất cả account đã có data. Không có gì để scrape.")
            return 0

    print(f"Sẽ scrape {len(accounts)} account HTTP cho ngày {metric_date} "
          f"({args.max_workers} workers song song)")

    results = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futs = {ex.submit(_scrape_one, a, metric_date): a for a in accounts}
        for fut in as_completed(futs):
            a = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:
                rec = _finalize({
                    "platform": a["platform"], "label": a["label"],
                    "owner": a.get("owner", ""), "email": a.get("email", ""),
                    "metric_date": metric_date.isoformat(),
                    "error": f"{type(e).__name__}: {e}",
                })
                save_metric(rec)
            results.append(rec)
            tag = "✗" if rec.get("error") else "✓"
            money = rec.get("total_earned")
            extra = f"earned={money} {rec.get('currency') or ''}" if money is not None else ""
            print(f"  {tag} [{rec['platform']}/{rec['label']}] {rec.get('error') or extra}")

    success = sum(1 for r in results if not r.get("error"))
    print(f"\n=== Tổng kết: {success} ok, {len(results)-success} lỗi (trên {len(results)}) ===")

    if not args.no_sheet and results:
        from core.sheet_sync import push_to_sheet
        print(f"Đẩy {len(results)} dòng lên Google Sheet...")
        resp = push_to_sheet(results)
        if resp.get("ok"):
            print(f"  ✓ Sheet ghi {resp.get('written')} dòng.")
        else:
            print(f"  ✗ Sheet error: {resp.get('error') or resp}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
