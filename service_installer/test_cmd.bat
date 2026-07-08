@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion

echo Step 1: Writing temp file...
powershell -Command "$p=$null; foreach ($d in @(($env:LOCALAPPDATA+'\Programs\Inno Setup 6'),([Environment]::GetEnvironmentVariable('ProgramFiles(x86)')+'\Inno Setup 6'),($env:ProgramFiles+'\Inno Setup 6'))) { if (Test-Path (Join-Path $d 'ISCC.exe')) { $p=Join-Path $d 'ISCC.exe'; break } }; Write-Output $p" > "%TEMP%\iscc_path.txt" 2>nul

echo Step 2: File contents...
type "%TEMP%\iscc_path.txt"

echo Step 3: Reading via for /f...
for /f "usebackq delims=" %%r in ("%TEMP%\iscc_path.txt") do (
    echo Read line: [%%r]
)

del "%TEMP%\iscc_path.txt" 2>nul
echo Done
