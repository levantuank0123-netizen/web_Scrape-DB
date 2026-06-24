"""Runner chạy scraper qua nhiều GPM profile (mỗi email = 1 profile).

Usage:
  python -m core.runner --all
  python -m core.runner --platform getrewardful
  python -m core.runner --account alphana-ai
  python -m core.runner --owner Dũng
  python -m core.runner --platform getrewardful --parallel    # mở 5 profile cùng lúc
"""
from __future__ import annotations
import argparse
import sys
import traceback
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, timedelta
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
from core.gpm import open_profile
from core.sheet_sync import push_to_sheet
from scrapers import get_scraper


def parse_date(s: str) -> date:
    from datetime import datetime
    return datetime.strptime(s, "%Y-%m-%d").date()


def _finalize(record: dict) -> dict:
    if record.get("error"):
        msg, perm = classify_error(record["error"])
        record["error"] = msg
        record["error_permanent"] = 1 if perm else 0
    else:
        record["error"] = None
        record["error_permanent"] = 0
    return record


def scrape_email_group(args_tuple):
    """Worker function: scrape tất cả dashboard của 1 email trong 1 profile.

    args_tuple = (email, accounts_list, metric_date_iso, keep_open)
    Trả về list of records (đã finalize, đã save_metric).
    """
    email, accounts, metric_date_iso, keep_open = args_tuple
    # Re-import trong process con (vì ProcessPoolExecutor spawn)
    from datetime import datetime
    metric_date = datetime.strptime(metric_date_iso, "%Y-%m-%d").date()

    from core.db import save_metric
    from core.gpm import open_profile
    from scrapers import get_scraper

    results = []
    print(f"\n========== [WORKER] Profile: {email} ({len(accounts)} dashboard) ==========")
    # Delay giữa các dashboard để tránh rate limit
    INTER_DASHBOARD_DELAY_SEC = 8
    try:
        with open_profile(email=email, close_when_done=not keep_open) as (browser, page):
            for i, acc in enumerate(accounts):
                if i > 0:
                    import time as _t
                    _t.sleep(INTER_DASHBOARD_DELAY_SEC)
                    # Ngắt navigation đang dang dở (tránh race condition)
                    try:
                        page.evaluate("window.stop()")
                    except Exception:
                        pass
                plat = acc["platform"]
                label = acc["label"]
                print(f"  [{email}] [{plat}/{label}] start")
                try:
                    ScraperCls = get_scraper(plat)
                    scraper = ScraperCls(acc)
                    result = scraper.run(page, metric_date=metric_date)
                    result = _finalize(result)
                except Exception as e:
                    result = _finalize({
                        "platform": plat,
                        "label": label,
                        "owner": acc.get("owner", ""),
                        "email": acc.get("email", ""),
                        "metric_date": metric_date.isoformat(),
                        "error": f"{type(e).__name__}: {e}",
                    })
                save_metric(result)
                results.append(result)
                tag = "✗" if result.get("error") else "✓"
                print(f"  [{email}] [{plat}/{label}] {tag} error={result.get('error') or '-'}")
    except Exception as e:
        print(f"  [{email}] LỖI mở profile: {e}")
        for acc in accounts:
            err = _finalize({
                "platform": acc["platform"],
                "label": acc["label"],
                "owner": acc.get("owner", ""),
                "email": acc.get("email", ""),
                "metric_date": metric_date.isoformat(),
                "error": f"profile open error: {e}",
            })
            save_metric(err)
            results.append(err)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--platform")
    ap.add_argument("--account", help="Lọc theo label")
    ap.add_argument("--owner", help="Lọc theo người quản (Dũng/An/Hà)")
    ap.add_argument("--limit", type=int, help="Giới hạn số account (test)")
    ap.add_argument("--date", help="YYYY-MM-DD, mặc định = hôm qua")
    ap.add_argument("--keep-open", action="store_true")
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--force", action="store_true", help="Chạy lại cả account đã có data")
    ap.add_argument("--parallel", action="store_true", help="Mở nhiều profile cùng lúc (1 worker / email)")
    ap.add_argument("--max-workers", type=int, default=5, help="Số worker tối đa khi --parallel (mặc định 5)")
    args = ap.parse_args()

    if not (args.all or args.platform or args.account or args.owner):
        ap.error("Phải chọn --all, --platform, --account hoặc --owner")

    metric_date = parse_date(args.date) if args.date else (date.today() - timedelta(days=1))
    accounts = load_accounts(
        only_active=True,
        label=args.account,
        platform=args.platform,
        owner=args.owner,
    )
    if not accounts:
        print("Không có tài khoản nào khớp. Kiểm tra accounts.xlsx.")
        return 1

    if args.limit:
        accounts = accounts[: args.limit]

    skipped = 0
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

    # Group theo email
    by_email: dict[str, list[dict]] = defaultdict(list)
    for a in accounts:
        by_email[a.get("email", "")].append(a)

    print(f"Sẽ scrape {len(accounts)} dashboard cho ngày {metric_date}")
    print(f"Phân thành {len(by_email)} nhóm theo email:")
    for em, acs in by_email.items():
        print(f"  - {em or '(no email)'}: {len(acs)} dashboard")

    metric_date_iso = metric_date.isoformat()
    all_results: list[dict] = []

    if args.parallel and len(by_email) > 1:
        # Parallel: 1 worker / email
        max_workers = min(args.max_workers, len(by_email))
        print(f"\n>>> Chạy PARALLEL với {max_workers} workers <<<")
        task_args = [
            (email, accs, metric_date_iso, args.keep_open)
            for email, accs in by_email.items()
        ]
        with ProcessPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(scrape_email_group, ta): ta[0] for ta in task_args}
            for fut in as_completed(futures):
                email = futures[fut]
                try:
                    results = fut.result()
                    all_results.extend(results)
                    print(f"\n[DONE] Profile {email}: {len(results)} kết quả")
                except Exception as e:
                    print(f"\n[FAIL] Profile {email}: {e}")
                    traceback.print_exc()
    else:
        # Sequential
        for email, accs in by_email.items():
            results = scrape_email_group(
                (email, accs, metric_date_iso, args.keep_open)
            )
            all_results.extend(results)

    success = sum(1 for r in all_results if not r.get("error"))
    fail = len(all_results) - success
    print(f"\n=== Tổng kết: {success} ok, {fail} lỗi (trên {len(all_results)} dashboard) ===")

    if not args.no_sheet and all_results:
        print(f"Đẩy {len(all_results)} dòng lên Google Sheet...")
        resp = push_to_sheet(all_results)
        if resp.get("ok"):
            print(f"  ✓ Sheet ghi {resp.get('written')} dòng.")
        else:
            print(f"  ✗ Sheet error: {resp.get('error') or resp}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
