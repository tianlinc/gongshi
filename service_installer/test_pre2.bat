@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion

REM ---- 预先检测 Inno Setup 6 ISCC.exe ----
set ISCC=
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

echo ISCC result: [%ISCC%]
if defined ISCC (echo ISCC FOUND: %ISCC%) else (echo ISCC NOT FOUND)
