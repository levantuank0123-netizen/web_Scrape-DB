"""Post-migration: Sau khi đã import 5 profile sang GPM mới, script này:
  - Đọc danh sách profile từ GPM mới qua Local API
  - Match theo NAME (email) → lấy profile_id mới
  - Update config/gpm.json
  - Re-apply proxy nếu bị mất
  - Verify bằng cách start 1 profile + check IP

Usage: python migrate_apply.py
"""
from __future__ import annotations
import json
import urllib.request
from pathlib import Path

GPM_HOST = "127.0.0.1:19995"
CONFIG_PATH = Path(__file__).parent / "config" / "gpm.json"
BACKUP_DIR = Path(__file__).parent / "data"


def fetch(url, method="GET", body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    if body:
        req.add_header("Content-Type", "application/json")
    return json.loads(urllib.request.urlopen(req, timeout=15).read().decode())


def main():
    # Tìm backup file mới nhất
    backups = sorted(BACKUP_DIR.glob("gpm_backup_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        print("✗ Không tìm thấy backup file. Chạy migrate_backup.py trước.")
        return 1
    backup = json.loads(backups[0].read_text(encoding="utf-8"))
    print(f"✓ Loaded backup: {backups[0].name}")

    # Lấy danh sách profile từ GPM mới
    try:
        resp = fetch(f"http://{GPM_HOST}/api/v3/profiles?page=1&per_page=200")
        new_profiles = {p["name"]: p for p in resp.get("data", [])}
    except Exception as e:
        print(f"✗ Không kết nối được GPM Local API: {e}")
        print("  → Mở GPM mới, bật Local API, thử lại.")
        return 1

    print(f"✓ Tìm thấy {len(new_profiles)} profile trong GPM mới")
    print()

    # Match theo email (= profile name)
    email_to_new_pid = {}
    missing = []
    for prof in backup["profiles"]:
        email = prof["email"]
        if email in new_profiles:
            new_id = new_profiles[email]["id"]
            email_to_new_pid[email] = new_id
            print(f"  ✓ {email:35s} → {new_id}")
        else:
            missing.append(email)
            print(f"  ✗ {email:35s} CHƯA TÌM THẤY trong GPM mới")

    if missing:
        print()
        print(f"⚠ Thiếu {len(missing)} profile. Hãy import vào GPM mới rồi chạy lại.")
        return 1

    # Re-apply proxy nếu mất
    print()
    print("=== Verify + re-apply proxy ===")
    for prof in backup["profiles"]:
        new_pid = email_to_new_pid[prof["email"]]
        old_proxy = prof.get("raw_proxy") or ""
        try:
            cur = fetch(f"http://{GPM_HOST}/api/v3/profiles/{new_pid}")["data"]
            cur_proxy = cur.get("raw_proxy") or ""
            if cur_proxy != old_proxy:
                print(f"  • {prof['email']:35s} proxy mismatch → re-applying")
                fetch(
                    f"http://{GPM_HOST}/api/v3/profiles/update/{new_pid}",
                    method="PUT",
                    body={"raw_proxy": old_proxy, "proxy_type": "http" if old_proxy else ""},
                )
            else:
                print(f"  ✓ {prof['email']:35s} proxy OK")
        except Exception as e:
            print(f"  ✗ {prof['email']:35s} ERROR: {e}")

    # Update config/gpm.json
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg["email_to_profile"] = email_to_new_pid
    if email_to_new_pid.get("tranthu431983@gmail.com"):
        cfg["default_profile_id"] = email_to_new_pid["tranthu431983@gmail.com"]
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print(f"✓ Updated {CONFIG_PATH}")
    print()
    print("--- BƯỚC TIẾP THEO ---")
    print("1. Test 1 dashboard: python -m core.runner --account alphana-ai --no-sheet")
    print("2. Nếu OK, chờ cron 7h sáng mai tự chạy.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
