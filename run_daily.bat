@echo off
chcp 65001 >nul
cd /d "E:\ADS\Claude\affiliate-scraper"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value 2^>nul ^| find "="') do set dt=%%a
set ymd=%dt:~0,4%-%dt:~4,2%-%dt:~6,2%
echo === Run start %ymd% === >> "logs\daily_%ymd%.log" 2>&1
"C:\Users\Admin\AppData\Local\Python\bin\python.exe" -X utf8 -m core.runner --all >> "logs\daily_%ymd%.log" 2>&1
echo === Run end %ymd% === >> "logs\daily_%ymd%.log" 2>&1
