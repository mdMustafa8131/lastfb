@echo off
cd /d %~dp0
git add -A
git commit -m "settings update"
git push
echo.
echo Ho gaya.
pause