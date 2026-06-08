@echo off
title SportsBetting - Lancement
cd /d "%~dp0"

echo ================================================
echo   SportsBetting - The Odds API (server_lite)
echo ================================================
echo.
echo Mise a jour depuis GitHub...
git pull origin master

echo.
echo Installation Flask...
pip install flask flask-cors requests -q 2>nul

echo.
echo Demarrage du serveur (The Odds API)...
start "SportsBetting-API-LITE" cmd /k "cd /d %~dp0 && echo Serveur server_lite.py en cours... && python api\server_lite.py"

echo Attente 5 secondes...
timeout /t 5 /nobreak > nul

echo Demarrage tunnel Cloudflare...
start "SportsBetting-Tunnel" cmd /k "cd /d %~dp0\api && tunnel.bat"

echo.
echo ================================================
echo   LANCE ! Attendez la ligne :
echo   [HH:MM] Raffraichi - XX arbitrages
echo   dans la fenetre SportsBetting-API-LITE
echo.
echo   Puis allez sur :
echo   https://sports-betting-xi-nine.vercel.app
echo ================================================
pause
