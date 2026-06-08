@echo off
title SportsBetting - Lancement complet
cd /d "%~dp0"

echo ================================================
echo   SportsBetting - Lancement automatique
echo ================================================
echo.
echo Mise a jour depuis GitHub...
git pull origin master

echo.
echo Installation des dependances...
pip install flask flask-cors requests -q

echo.
echo Demarrage du serveur API dans une nouvelle fenetre...
start "SportsBetting API" cmd /k "cd /d "%~dp0" && python api\server_lite.py"

echo Attente du demarrage du serveur (5 secondes)...
timeout /t 5 /nobreak > nul

echo Demarrage du tunnel Cloudflare dans une nouvelle fenetre...
start "SportsBetting Tunnel" cmd /k "cd /d "%~dp0\api" && tunnel.bat"

echo.
echo ================================================
echo   TOUT EST LANCE !
echo.
echo   1. Attendez que le tunnel affiche son URL
echo      (ex: https://xxxxx.trycloudflare.com)
echo.
echo   2. Ouvrez le dashboard :
echo      https://sports-betting-xi-nine.vercel.app
echo.
echo   3. Double-cliquez sur le logo pour entrer l'URL
echo      du tunnel si necessaire.
echo.
echo   Ne fermez pas les fenetres "API" et "Tunnel".
echo ================================================
echo.
pause
