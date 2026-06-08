@echo off
title SportsBetting API
echo ================================================
echo   SportsBetting Dashboard - Serveur API
echo ================================================
echo.

REM Installe les dependances si necessaire
pip install flask flask-cors requests beautifulsoup4 lxml 2>nul

echo.
echo Demarrage de l'API sur http://localhost:5000
echo.

REM Lance depuis le dossier racine du projet
cd /d "%~dp0.."
python api/server_lite.py

pause
