"""Pre-migration: Backup metadata 5 profile GPM hiện tại trước khi chuyển sang GPM mới.

Output: data/gpm_backup_<timestamp>.json
  - list 5 profile (id, name, raw_proxy, proxy_type, group_id)
  - config/gpm.json hiện tại
  - mapping email → proxy

Sau khi backup xong, mày làm 3 việc trong GPM cũ:
  1. Export 5 profile → save .gpm file
  2. Login GPM mới
  3. Import 5 profile vào GPM mới
  4. Chạy migrate_apply.py để auto-update config
"""
from __future__ import annotations
import json
import urllib.request
from pathlib import Path
from datetime import datetime

GPM_HOST = "127.0.0.1:19995"
CONFIG_PATH = Path(__file__).parent / "config" / "gpm.json"
BACKUP_DIR = Path(__file__).parent / "data"


def fetch(url):
    return json.loads(urllib.request.urlopen(url, timeout=10).read().decode())


def main():
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    email_to_pid = cfg.get("email_to_profile", {})

    # Lấy chi tiết từng profile
    profiles = []
    for email, pid in email_to_pid.items():
        try:
            d = fetch(f"http://{GPM_HOST}/api/v3/profiles/{pid}")["data"]
            profiles.append({
                "email": email,
                "id_OLD": pid,
                "name": d.get("name"),
                "raw_proxy": d.get("raw_proxy"),
                "browser_version": d.get("browser_version"),
                "group_id_OLD": d.get("group_id"),
            })
        except Exception as e:
            profiles.append({"email": email, "id_OLD": pid, "error": str(e)})

    # Lấy danh sách group
    try:
        groups = fetch(f"http://{GPM_HOST}/api/v3/groups")["data"]
    except Exception:
        groups = []

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"gpm_backup_{timestamp}.json"
    backup = {
        "timestamp": timestamp,
        "old_gpm_host": GPM_HOST,
        "old_config": cfg,
        "profiles": profiles,
        "groups": groups,
        "note": "Profile name = email. Sau khi import vào GPM mới, chạy migrate_apply.py để map name → id mới.",
    }
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(json.dumps(backup, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✓ Backup saved: {backup_path}")
    print()
    print("=== 5 profile cần export → import sang GPM mới ===")
    for p in profiles:
        print(f"  • {p['email']:35s} (id: {p.get('id_OLD')[:8]}... proxy: {(p.get('raw_proxy') or '(local)')[:30]})")
    print()
    print("--- HƯỚNG DẪN ---")
    print("1. Trong GPM CŨ: chọn 5 profile → Export → save file .gpm/.zip")
    print("2. Login GPM MỚI bằng tài khoản administrator")
    print("3. Trong GPM MỚI: Import file vừa export")
    print("4. Đảm bảo group 'AFF Dashboard' tồn tại (tạo mới nếu chưa có)")
    print("5. Chạy: python migrate_apply.py")


if __name__ == "__main__":
    main()
