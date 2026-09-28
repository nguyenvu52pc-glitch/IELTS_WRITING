@echo off
title ENTERPRISE TIMECLOCK SAAS PRO - SERVER & CLOUDFLARE TUNNEL
color 0C

echo ======================================================================
echo    ENTERPRISE TIMECLOCK SAAS PRO (V3.8 - GOOGLE WHITELIST EDITION)
echo ======================================================================
echo.
echo [1/3] Khoi dong Server Backend (Python FastAPI)...
start "Backend Server" /min python server.py

timeout /t 2 /nobreak >nul

echo [2/3] Khoi dong Cloudflare Tunnel (Tao link Internet mien phi)...
start "Cloudflare Tunnel" /min cloudflared.exe tunnel --url http://127.0.0.1:8000

timeout /t 3 /nobreak >nul

echo [3/3] Dang mo giao dien Kiosk tren may tinh...
start http://127.0.0.1:8000

echo.
echo ======================================================================
echo  HE THONG DA KHOI CHAY THANH CONG!
echo  - Kiosk Noi bo (May ban):  http://127.0.0.1:8000
echo  - Kiosk Mang Wi-Fi LAN:   http://192.168.1.87:8000
echo  - Quan tri Admin Server:  http://127.0.0.1:8000/admin (Pass: admin@saas2026)
echo ======================================================================
echo.
echo Giu nguyen cua so nay de he thong hoat dong.
pause
