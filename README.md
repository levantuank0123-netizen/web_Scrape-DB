# Affiliate Dashboard Scraper

Tự động lấy metrics từ dashboard của 100+ tài khoản affiliate mỗi sáng 7h.

## Cấu trúc

```
affiliate-scraper/
├── accounts.xlsx           # Danh sách tài khoản (mày điền vào đây)
├── config/
│   └── google_sheet.json   # Service account key cho Google Sheets
├── core/
│   ├── runner.py           # Chạy tất cả scraper
│   ├── db.py               # SQLite storage
│   └── sheet_sync.py       # Push lên Google Sheet
├── scrapers/
│   ├── _base.py            # Base class
│   ├── tolt.py             # Adapter Tolt
│   ├── affiliatly.py       # ...
│   └── ...
├── data/
│   ├── metrics.db          # SQLite chứa metrics theo ngày
│   └── sessions/           # Cookie cache mỗi tài khoản
└── logs/
```

## Quy ước cột Excel `accounts.xlsx`

| platform | label | email | password | login_url | dashboard_url | notes |
|----------|-------|-------|----------|-----------|---------------|-------|
| tolt | store-abc | a@b.com | xxx | https://app.tolt.io/login | (auto) | |

## Chạy thử

```bash
python -m core.runner --platform tolt --account store-abc
```

## Chạy hàng ngày

Windows Task Scheduler chạy `python -m core.runner --all` lúc 7:00 AM.
