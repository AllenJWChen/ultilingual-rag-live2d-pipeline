@echo off
setlocal enableextensions enabledelayedexpansion

rem 目前所在資料夾
set "HERE=%cd%"
set "DIR=%HERE%"

:search
rem 在目前層找 .venv
if exist "%DIR%\.venv\Scripts\Activate.ps1" goto found

rem 取父資料夾
for %%i in ("%DIR%\..") do set "NEXT=%%~fi"

rem 到了根目錄就停
if /I "%NEXT%"=="%DIR%" goto notfound

set "DIR=%NEXT%"
goto search

:found
echo ✅ 找到虛擬環境：%DIR%\.venv
start powershell -NoExit -Command "Set-Location '%HERE%'; & '%DIR%\.venv\Scripts\Activate.ps1'"
exit /b 0

:notfound
echo ❌ 沒找到鄰近的 .venv，請先建立： py -m venv .venv
pause
exit /b 1
