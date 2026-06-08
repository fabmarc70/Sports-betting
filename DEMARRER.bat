@echo off
title SportsBetting API - LITE
echo ================================================
echo   SportsBetting Dashboard - Serveur API LITE
echo ================================================
echo.
echo Installation des dependances...
pip install flask flask-cors requests -q

echo.
echo Demarrage de l'API sur http://localhost:5000
echo (Appuyez sur Ctrl+C pour arreter)
echo.

python "%~dp0api\server_lite.py"

echo.
echo Le serveur s'est arrete.
pause
