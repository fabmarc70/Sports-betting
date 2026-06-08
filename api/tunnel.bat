@echo off
title CloudFlare Tunnel - SportsBetting
echo ================================================
echo   Tunnel Cloudflare pour SportsBetting API
echo ================================================
echo.
echo Ce script expose votre API locale sur Internet.
echo Copiez l'URL https://xxxxx.trycloudflare.com
echo et collez-la dans la variable API_URL du dashboard.
echo.

REM Telecharge cloudflared si absent
if not exist "%~dp0cloudflared.exe" (
    echo Telechargement de cloudflared...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile '%~dp0cloudflared.exe'"
)

echo Lancement du tunnel...
"%~dp0cloudflared.exe" tunnel --url http://localhost:5000

pause
