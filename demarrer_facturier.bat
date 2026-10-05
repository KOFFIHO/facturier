@echo off

cd /d "C:\Users\honor\Desktop\DEVE_KOFFI\facturier_mvt"

call venv\Scripts\activate.bat

start "" cmd /c "timeout /t 5 /nobreak >nul & start http://127.0.0.1:8000/"

python manage.py runserver 127.0.0.1:8000