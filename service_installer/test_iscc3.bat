@echo off
setlocal enabledelayedexpansion

echo Testing build.bat ISCC detection logic...

set ISCC=
REM 常见安装路径
for %%d in (
    "C:\Program Files (x86)\Inno Setup 6"
    "C:\Program Files\Inno Setup 6"
    "%LOCALAPPDATA%\Programs\Inno Setup 6"
) do (
    if exist "%%~d\ISCC.exe" (
        set "ISCC=%%~d\ISCC.exe"
    )
)

echo [DEBUG] ISCC after for loop: [%ISCC%]

REM 检查 PATH 中是否有
if not defined ISCC (
    where iscc >nul 2>&1
    if not errorlevel 1 set "ISCC=iscc"
)

echo [DEBUG] ISCC before PS fallback: [%ISCC%]

REM PowerShell 回退检测
if not defined ISCC (
    powershell -Command "$p=$null; foreach ($d in @(($env:LOCALAPPDATA+'\Programs\Inno Setup 6'),([Environment]::GetEnvironmentVariable('ProgramFiles(x86)')+'\Inno Setup 6'),($env:ProgramFiles+'\Inno Setup 6'))) { if (Test-Path (Join-Path $d 'ISCC.exe')) { $p=Join-Path $d 'ISCC.exe'; break } }; Write-Output $p" > "%TEMP%\iscc_path.txt" 2>nul
    for /f "usebackq delims=" %%r in ("%TEMP%\iscc_path.txt") do (
        if not "%%r"=="" set "ISCC=%%r"
    )
    del "%TEMP%\iscc_path.txt" 2>nul
)

echo [DEBUG] ISCC after all detection: [%ISCC%]

if not defined ISCC (
    echo ISCC NOT FOUND
) else (
    echo [OK] ISCC found: %ISCC%
)
