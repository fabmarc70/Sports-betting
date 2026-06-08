@echo off
title SportsBetting API - Betclic, Winamax, PMU, Unibet...
echo ================================================
echo   SportsBetting - Serveur COMPLET
echo   Bookmakers: Betclic, Winamax, PMU, Unibet,
echo               Bwin, Zebet, Parions Sport...
echo ================================================
echo.
echo Installation des dependances (peut prendre 2-3 min)...
echo.

pip install flask flask-cors requests -q
pip install selenium chromedriver-autoinstaller fake-useragent -q
pip install unidecode numpy beautifulsoup4 lxml termcolor colorama -q
pip install python-dateutil stopit tabulate pillow demjson3 scipy -q
pip install selenium-wire pyopenssl websockets -q

echo.
echo ================================================
echo   Demarrage du serveur sur http://localhost:5000
echo   Chrome va s'ouvrir automatiquement pour
echo   recuperer les cotes en temps reel.
echo   Ne fermez pas les fenetres Chrome.
echo ================================================
echo.

cd /d "%~dp0"
python api\server.py

pause
