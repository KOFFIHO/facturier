@echo off
rem Demarre le Facturier sur ce poste de caisse.
rem %~dp0 = dossier de ce fichier : marche quel que soit le dossier du projet,
rem y compris au demarrage automatique de Windows.
cd /d "%~dp0"

call venv\Scripts\activate.bat

start "" cmd /c "timeout /t 6 /nobreak >nul & start http://127.0.0.1:8000/"

python manage.py runserver 127.0.0.1:8000 --noreload
