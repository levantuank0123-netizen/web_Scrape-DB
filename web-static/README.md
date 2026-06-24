# Affiliate Dashboard — Static frontend

Deployed on Netlify. Fetches data from Google Apps Script webhook.

## Local test
Mở `index.html` trực tiếp bằng browser. Hoặc:
```bash
python -m http.server 8000 -d web-static
# → http://localhost:8000
```

## Deploy

1. Push folder này lên GitHub repo
2. Netlify → New site from Git → connect repo
3. Build settings: leave default (netlify.toml has it)
4. Deploy

## Config

URL Apps Script webhook nằm trong `app.js`. Đã hardcode sẵn.
