@echo off
echo CFO Agent Launcher
echo -----------------

echo Checking and fixing environment file...
py -3 fix_env_file.py

echo.
echo Starting CFO Agent...
streamlit run main.py

echo.
echo Application closed.
pause 