@echo off
chcp 65001 >nul
cd /d "E:\ADS\Claude\affiliate-scraper"
set PYTHONIOENCODING=utf-8
echo Starting Affiliate Scraper Web App on http://localhost:5000 ...
start "" "http://localhost:5000"
"C:\Users\Admin\AppData\Local\Python\bin\python.exe" -X utf8 web/app.py
