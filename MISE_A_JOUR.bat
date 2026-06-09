@echo off
title SportsBetting - Mise a jour
cd /d "%~dp0"
color 0E

echo.
echo  ============================================
echo    SportsBetting - Mise a jour rapide
echo    Le tunnel NE sera PAS redémarre.
echo    L URL Cloudflare reste la meme.
echo  ============================================
echo.

REM --- Arret du serveur Flask UNIQUEMENT (par port 5000) ---
REM    On ne touche PAS aux autres processus Python (trading, etc.)
echo  Arret du serveur Flask (port 5000)...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":5000 "') do (
    taskkill /F /PID %%a 2>nul
)
REM Ferme aussi la fenetre cmd du serveur si elle existe
taskkill /F /FI "WINDOWTITLE eq SportsBetting-SERVEUR" 2>nul
timeout /t 1 /nobreak > nul

REM --- Mise a jour du code ---
echo  Recuperation du nouveau code...
git pull origin master

REM --- Redemarrage du serveur uniquement ---
echo  Redemarrage du serveur...
start "SportsBetting-SERVEUR" cmd /k "title SportsBetting-SERVEUR && cd /d %~dp0 && python api\server_lite.py"

echo.
echo  ============================================
echo    Serveur redémarre avec le nouveau code.
echo    Le tunnel et l URL sont INCHANGES.
echo    Attendez la ligne [HH:MM] Rafraichi...
echo    dans la fenetre SportsBetting-SERVEUR.
echo  ============================================
echo.
timeout /t 3 /nobreak > nul
exit
