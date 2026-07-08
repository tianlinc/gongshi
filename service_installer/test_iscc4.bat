@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion

set ISCC=
echo [TEST] Running ISCC detection...

powershell -Command "$p=$null; foreach ($d in @(($env:LOCALAPPDATA+'\Programs\Inno Setup 6'),([Environment]::GetEnvironmentVariable('ProgramFiles(x86)')+'\Inno Setup 6'),($env:ProgramFiles+'\Inno Setup 6'))) { if (Test-Path (Join-Path $d 'ISCC.exe')) { $p=Join-Path $d 'ISCC.exe'; break } }; Write-Output $p" > "%TEMP%\iscc_path.txt" 2>nul

echo [TEST] Temp file check:
type "%TEMP%\iscc_path.txt"

for /f "usebackq delims=" %%r in ("%TEMP%\iscc_path.txt") do (
    echo [TEST] Read from file: [%%r]
    if not "%%r"=="" set "ISCC=%%r"
)

del "%TEMP%\iscc_path.txt" 2>nul
echo [TEST] ISCC after detection: [%ISCC%]
if defined ISCC (echo [TEST] ISCC IS defined) else (echo [TEST] ISCC NOT defined)
