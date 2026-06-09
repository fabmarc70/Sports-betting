@echo off
title SportsBetting - Lancement initial
cd /d "%~dp0"
color 0A

echo.
echo  ============================================
echo    SportsBetting - Premier lancement
echo  ============================================
echo.

REM --- Mise a jour du code ---
echo  [1/3] Mise a jour depuis GitHub...
git pull origin master
echo.

REM --- Dependances ---
echo  [2/3] Installation des dependances...
pip install flask flask-cors requests -q 2>nul

REM --- Serveur Flask ---
echo  [3/3] Demarrage du serveur API...
start "SportsBetting-SERVEUR" cmd /k "title SportsBetting-SERVEUR && cd /d %~dp0 && python api\server_lite.py"

echo  Attente 4 secondes...
timeout /t 4 /nobreak > nul

REM --- Tunnel Cloudflare ---
echo  Demarrage du tunnel Cloudflare...
start "SportsBetting-TUNNEL" cmd /k "title SportsBetting-TUNNEL && cd /d %~dp0\api && tunnel.bat"

echo.
echo  ============================================
echo.
echo    ETAPE SUIVANTE :
echo    Dans la fenetre SportsBetting-TUNNEL,
echo    copiez l URL https://xxxxx.trycloudflare.com
echo    et collez-la dans le dashboard Vercel.
echo.
echo    Le tunnel tourne en permanence.
echo    Pour mettre a jour le code : MISE_A_JOUR.bat
echo    Pour tout arreter le soir  : ARRETER.bat
echo.
echo  ============================================
echo.
pause
