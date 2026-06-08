@echo off
title SportsBetting API
echo ================================================
echo   SportsBetting Dashboard - Serveur API
echo ================================================
echo.

REM Installe les dependances si necessaire
pip install flask flask-cors 2>nul

echo Demarrage de l'API sur http://localhost:5000
echo.

REM Lance l'API depuis le dossier racine du projet
cd /d "%~dp0.."
python api/server.py

pause
