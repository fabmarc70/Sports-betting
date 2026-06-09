@echo off
title SportsBetting - Arret
cd /d "%~dp0"
color 0C

echo.
echo  ============================================
echo    SportsBetting - Arret complet
echo  ============================================
echo.

REM Arrete le serveur Flask (port 5000 uniquement)
echo  Arret du serveur Flask...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":5000 "') do (
    taskkill /F /PID %%a 2>nul
)
taskkill /F /FI "WINDOWTITLE eq SportsBetting-SERVEUR" 2>nul

REM Arrete le tunnel Cloudflare
echo  Arret du tunnel Cloudflare...
taskkill /F /FI "WINDOWTITLE eq SportsBetting-TUNNEL" 2>nul
taskkill /F /FI "WINDOWTITLE eq CloudFlare Tunnel - SportsBetting" 2>nul
taskkill /F /IM "cloudflared.exe" 2>nul

echo.
echo  Tout est arrete. Bonne nuit !
echo.
timeout /t 3 /nobreak > nul
exit
