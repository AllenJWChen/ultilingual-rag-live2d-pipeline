@echo off
setlocal enableextensions enabledelayedexpansion

rem 目前所在資料夾
set "HERE=%cd%"
set "DIR=%HERE%"

:search
rem 在目前層找 .venv
if exist "%DIR%\.venv\Scripts\activate.bat" goto found

rem 取父資料夾：用 .. 保證真的往上
for %%i in ("%DIR%\..") do set "NEXT=%%~fi"

rem 到了根目錄就停
if /I "%NEXT%"=="%DIR%" goto notfound

set "DIR=%NEXT%"
goto search

:found
cd /d "%HERE%"
echo 啟動虛擬環境：%DIR%
call "%DIR%\.venv\Scripts\activate.bat"
echo 目前路徑：%cd%
cmd
exit /b 0

:notfound
echo 沒找到鄰近的 .venv，請先建立：  py -m venv .venv
pause
exit /b 1
